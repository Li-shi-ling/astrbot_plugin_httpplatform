"""
HTTP/HTTPS Platform Adapter for AstrBot

此适配器提供 HTTP/HTTPS 接口，让外部应用可以通过 HTTP 访问 AstrBot。
内部会将 HTTP 请求转换为 WebSocket 通信，并将响应返回给 HTTP 客户端。
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, Optional
from collections.abc import Coroutine

import hmac
from quart import Quart, request, jsonify, make_response
from quart_cors import cors

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.astr_message_event import MessageSesion

# 导入常量和数据类
from .constants import HTTP_MESSAGE_TYPE, HTTP_STATUS_CODE
from .dataclasses import HTTPRequestData, PendingResponse
from .httpmessageevent import StandardHTTPMessageEvent, StreamHTTPMessageEvent
from .tool import Json2BMCChain

# ==================== HTTP 适配器主类 ====================
class HTTPAdapter(Platform):
    """HTTP/HTTPS 平台适配器实现"""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.settings = platform_settings
        self.config = platform_config

        # HTTP 服务器配置
        self.http_host = platform_config.get("http_host", "0.0.0.0")
        self.http_port = int(platform_config.get("http_port", 8080))
        self.api_prefix = platform_config.get("api_prefix", "/api/v1").rstrip("/")
        self.enable_http_api = platform_config.get("enable_http_api", True)
        self.auth_token = platform_config.get("auth_token", "")
        self.cors_origins = platform_config.get("cors_origins", "*")
        if isinstance(self.cors_origins, str):
            self.cors_origins = self.cors_origins.split(",")

        # 统计信息
        self.total_requests_processed = 0
        self.total_errors = 0

        # 会话管理
        self.pending_responses: Dict[str, PendingResponse] = {}

        # Quart 应用
        self.app = Quart(__name__)

        # 处理 CORS 来源配置
        cors_origins_config = platform_config.get("cors_origins", "*")
        if cors_origins_config == "*":
            cors_origins_list = "*"
        else:
            cors_origins_list = cors_origins_config.split(",") if isinstance(cors_origins_config, str) else cors_origins_config

        # 添加 CORS 支持 - 使用更全面的配置
        self.app = cors(
            self.app,
            allow_origin=cors_origins_list,
            allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
            allow_headers=["Content-Type", "Authorization", "Accept", "X-Request-ID", "Origin"],
            allow_credentials=False,
            expose_headers=["Content-Type", "Authorization", "X-Accel-Buffering"],
            max_age=86400,
        )

        self._setup_routes()

        # 运行状态
        self._running = False

        # 平台元数据
        platform_id = platform_config.get("id", "http_adapter_default")
        self._metadata = PlatformMetadata(
            name="http_adapter",
            description="HTTP/HTTPS 适配器 - 提供外部 HTTP 接口",
            id=platform_id,
            support_streaming_message=True,
            support_proactive_message=False,
        )

        self._background_tasks = set() # 用于追踪任务
        
        # 中断信号
        self.shutdown_event = asyncio.Event()

    def _start_task(self, coro: Coroutine):
        """统一管理后台任务，防止销毁报错"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def meta(self) -> PlatformMetadata:
        return self._metadata

    def _setup_routes(self):
        """设置 HTTP 路由"""

        # OPTIONS 预检请求处理 - 确保所有路径都支持 OPTIONS
        @self.app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
        @self.app.route('/<path:path>', methods=['OPTIONS'])
        async def options_handler(path):
            """处理所有 OPTIONS 预检请求"""
            response = await make_response('')
            response.status_code = HTTP_STATUS_CODE["OK"]

            # quart-cors 会自动处理 CORS 头部，我们只需要返回空响应
            return response

        # 健康检查
        @self.app.route(f'{self.api_prefix}/health', methods=['GET'])
        async def health_check():
            auth_result = await self._check_auth(request)
            if auth_result is not None:
                return auth_result
            return jsonify({
                "status": "ok",
                "service": "astrbot_http_adapter",
                "timestamp": time.time(),
                "pending_responses": len(self.pending_responses),
                "version": "1.0.0"
            })

        # 发送消息接口
        @self.app.route(f'{self.api_prefix}/message', methods=['POST', 'OPTIONS'])
        async def send_message():
            """发送消息到 AstrBot"""
            if request.method == 'OPTIONS':
                return '', HTTP_STATUS_CODE["OK"]
            return await self._handle_http_message(request)

        # 流式消息接口
        @self.app.route(f'{self.api_prefix}/message/stream', methods=['POST', 'OPTIONS'])
        async def send_message_stream():
            """流式发送消息到 AstrBot"""
            if request.method == 'OPTIONS':
                return '', HTTP_STATUS_CODE["OK"]
            return await self._handle_http_stream_message(request)

    async def _handle_http_message(self, request_obj) -> Any:
        """处理 HTTP 消息请求"""
        # 鉴权
        auth_result = await self._check_auth(request_obj)
        if auth_result is not None:
            return auth_result
        future = None
        event_id = None
        try:
            # 获取请求数据
            data = await request_obj.get_json()
            if not data:
                return jsonify({"error": "无效的请求数据"}), HTTP_STATUS_CODE["BAD_REQUEST"]

            # 收集请求头信息
            headers = dict(request_obj.headers)
            request_data = HTTPRequestData(
                method=request_obj.method,
                url=request_obj.url,
                headers=headers,
                remote_addr=request_obj.remote_addr,
                user_agent=request_obj.user_agent.string if request_obj.user_agent else None,
                content_type=request_obj.content_type,
                accept=request_obj.headers.get('Accept')
            )

            # 必需参数检查
            message = data.get('message', None)
            if not message:
                return jsonify({"error": "message 参数是必需的"}), HTTP_STATUS_CODE["BAD_REQUEST"]
            messages = None
            if isinstance(message, list):
                messages = Json2BMCChain(message)
            # 获取会话ID或创建新的
            platform = data.get('platform', "")
            user_id = data.get('user_id', '0')
            nickname = data.get('nickname', '外部用户')
            session_id = f"{platform}_{user_id}"

            # 创建事件并提交
            event_id = str(uuid.uuid4())
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            self.pending_responses[event_id] = PendingResponse(
                future=future,
                session_id=session_id,
                timeout=data.get('timeout', 30)
            )

            # 创建消息对象
            abm = AstrBotMessage()
            abm.self_id = str(self._metadata.id)
            abm.sender = MessageMember(
                user_id=str(user_id),
                nickname=nickname,
            )
            abm.type = MessageType.GROUP_MESSAGE
            abm.session_id = session_id
            abm.message_id = data.get('message_id', str(uuid.uuid4().hex))
            if messages is None:
                abm.message = [Plain(text=message)]
            else:
                abm.message = messages
            abm.message_str = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
            abm.raw_message = data
            abm.timestamp = int(time.time())

            # 创建事件
            event = StandardHTTPMessageEvent(
                message_str=message,
                message_obj=abm,
                platform_meta=self._metadata,
                session_id=session_id,
                adapter=self,
                event_id=event_id,
                request_data=request_data
            )

            # 设置额外信息
            event.set_extra("data", data)

            event.is_wake = True
            event.is_at_or_wake_command = True

            # 提交事件到队列
            self.commit_event(event)

            # 更新统计
            self.total_requests_processed += 1

            # 等待响应
            try:
                timeout = data.get('timeout', 30)
                if not isinstance(timeout, int):
                    logger.error(f"[HTTPAdapter] 不兼容的 timeout:{timeout} 尝试转变为 int")
                    timeout = int(timeout)
                if timeout < 0:
                    logger.error(f"[HTTPAdapter] timeout:{timeout} < 0 使用 30")
                    timeout = 30
                response = await asyncio.wait_for(future, timeout=timeout)

                # 构建响应
                response_data = {
                    "success": True,
                    "response": response,
                    "event_id": event_id,
                    "session_id": session_id,
                    "timestamp": time.time()
                }

                # 添加消息ID
                if 'message_id' in data:
                    response_data['message_id'] = data['message_id']

                return jsonify(response_data)

            except asyncio.TimeoutError:
                if event_id in self.pending_responses:
                    self.pending_responses.pop(event_id)
                return jsonify({
                    "error": "请求超时",
                    "event_id": event_id
                }), HTTP_STATUS_CODE["TIMEOUT"]

        except json.JSONDecodeError:
            self.total_errors += 1
            return jsonify({"error": "无效的 JSON 数据"}), HTTP_STATUS_CODE["BAD_REQUEST"]
        except Exception as e:
            self.total_errors += 1
            if future and not future.done():
                future.set_exception(e)
            logger.error(f"[HTTPAdapter] 处理HTTP请求时出错: {e}", exc_info=True)
            return jsonify({"error": f"内部服务器错误: {str(e)}"}), HTTP_STATUS_CODE["INTERNAL_ERROR"]
        finally:
            if not event_id is None:
                self.pending_responses.pop(event_id)

    async def _handle_http_stream_message(self, request_obj) -> Any:
        """处理 HTTP 流式消息请求 - 修复版，支持多条消息"""
        # 鉴权
        auth_result = await self._check_auth(request_obj)
        if auth_result is not None:
            return auth_result

        try:
            data = await request_obj.get_json()
            if not data:
                return jsonify({"error": "无效的请求数据"}), HTTP_STATUS_CODE["BAD_REQUEST"]

            message = data.get('message')
            if not message:
                return jsonify({"error": "message 参数是必需的"}), HTTP_STATUS_CODE["BAD_REQUEST"]
            if isinstance(message, list):
                messages = Json2BMCChain(message)
            else:
                # 如果是字符串，包装成 Plain 消息
                from astrbot.api.message_components import Plain
                messages = [Plain(text=str(message))]
            # 收集请求头信息
            headers = dict(request_obj.headers)
            request_data = HTTPRequestData(
                method=request_obj.method,
                url=request_obj.url,
                headers=headers,
                remote_addr=request_obj.remote_addr,
                user_agent=request_obj.user_agent.string if request_obj.user_agent else None,
                content_type=request_obj.content_type,
                accept=request_obj.headers.get('Accept')
            )

            platform = data.get('platform', "")
            user_id = data.get('user_id', '0')
            username = data.get('username', '外部用户')
            session_id = f"{platform}_{user_id}"

            # 创建 SSE 响应生成器
            async def generate():
                event_id = str(uuid.uuid4())
                queue = asyncio.Queue(maxsize=100)  # 增加队列大小

                # 创建消息对象
                abm = AstrBotMessage()
                abm.self_id = str(self._metadata.id)
                abm.sender = MessageMember(
                    user_id=str(user_id),
                    nickname=username,
                )
                abm.type = MessageType.GROUP_MESSAGE
                abm.session_id = session_id
                abm.message_id = str(uuid.uuid4().hex)
                abm.message = messages
                abm.message_str = message if isinstance(message, str) else json.dumps(message, ensure_ascii=False)
                abm.raw_message = data
                abm.timestamp = int(time.time())

                # 创建事件
                event = StreamHTTPMessageEvent(
                    message_str=message,
                    message_obj=abm,
                    platform_meta=self._metadata,
                    session_id=session_id,
                    adapter=self,
                    queue=queue,
                    event_id=event_id,
                    request_data=request_data
                )

                # 设置额外信息
                event.set_extra("original_data", data)

                event.is_wake = True
                event.is_at_or_wake_command = True

                # 提交事件
                self.commit_event(event)

                # 更新统计
                self.total_requests_processed += 1

                # 生成 SSE 流
                yield f"event: {HTTP_MESSAGE_TYPE['CONNECTED']}\ndata: {json.dumps({'event_id': event_id, 'session_id': session_id})}\n\n"

                # 设置超时参数
                timeout = data.get('timeout', 600)  # 增加到10分钟，支持长对话
                start_time = time.time()
                last_activity_time = time.time()
                received_end_event = False

                try:
                    while not received_end_event:
                        # 检查总超时
                        current_time = time.time()
                        if current_time - start_time > timeout:
                            yield (
                                f"event: {HTTP_MESSAGE_TYPE['TIMEOUT']}\n"
                                f"data: {json.dumps({'reason': 'total_timeout', 'duration': current_time - start_time})}\n\n"
                            )
                            break

                        # 检查活动超时（60秒无活动发送心跳）
                        if current_time - last_activity_time > 60:
                            # 发送心跳保持连接
                            yield f": heartbeat {int(current_time)}\n\n"
                            last_activity_time = current_time

                        try:
                            # 等待队列消息，使用短超时以便检查其他条件
                            item = await asyncio.wait_for(queue.get(), timeout=1.0)

                            if item is None:
                                # None 是特殊的结束信号
                                yield (
                                    f"event: {HTTP_MESSAGE_TYPE['END']}\n"
                                    f"data: {json.dumps({'reason': 'normal_end'})}\n\n"
                                )
                                received_end_event = True
                                break

                            # 处理事件
                            event_type = item.get('type')

                            # 更新最后活动时间
                            last_activity_time = time.time()

                            # 发送事件
                            yield (
                                f"event: {item.get('type')}\n"
                                f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                            )

                            # 如果是 end 事件，结束循环
                            if event_type == HTTP_MESSAGE_TYPE['END']:
                                received_end_event = True
                                break

                        except asyncio.TimeoutError:
                            # 超时是正常的，继续循环检查其他条件
                            continue

                except asyncio.CancelledError:
                    # 连接被取消
                    logger.info(f"[HTTPAdapter] SSE连接被取消: {event_id}")
                except Exception as e:
                    logger.error(f"[HTTPAdapter] 生成SSE时出错: {e}", exc_info=True)
                finally:
                    if event_id in self.pending_responses:
                        self.pending_responses.pop(event_id, None)
                    # 通知事件停止生成
                    try:
                        queue.put_nowait(None)
                    except:
                        pass
                    if hasattr(event, "_is_streaming"):
                        event._is_streaming = False
                    logger.info(f"[HTTPAdapter] SSE连接结束: {event_id}, 会话: {session_id}")

            headers = {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'X-Accel-Buffering': 'no',  # 禁用Nginx缓冲
                'X-Accel-Timeout': '1200',  # Nginx代理超时时间
            }

            return generate(), HTTP_STATUS_CODE["OK"], headers

        except json.JSONDecodeError:
            self.total_errors += 1
            return jsonify({"error": "无效的 JSON 数据"}), HTTP_STATUS_CODE["BAD_REQUEST"]
        except Exception as e:
            self.total_errors += 1
            logger.error(f"[HTTPAdapter] 处理流式请求时出错: {e}", exc_info=True)
            return jsonify({"error": f"内部服务器错误: {str(e)}"}), HTTP_STATUS_CODE["INTERNAL_ERROR"]

    async def _check_auth(self, request_obj) -> Optional[Any]:
        """检查鉴权"""
        if not self.auth_token:
            return None

        auth_header = request_obj.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "未授权访问"}), HTTP_STATUS_CODE["UNAUTHORIZED"]

        token = auth_header[7:]

        # 使用 hmac.compare_digest 进行安全的字符串比较
        if not hmac.compare_digest(token, self.auth_token):
            return jsonify({"error": "无效的令牌"}), HTTP_STATUS_CODE["UNAUTHORIZED"]

        return None

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        """通过会话发送消息"""
        # 对于 HTTP 适配器，这个功能由事件处理器处理
        pass

    def run(self) -> Coroutine[Any, Any, None]:
        """运行 HTTP 服务器"""
        return self._run_server()

    async def _run_server(self):
        """启动 HTTP 服务器"""
        if not self.enable_http_api:
            logger.info("[HTTPAdapter] HTTP API 已禁用")
            return

        logger.info(f"[HTTPAdapter] 启动 HTTP 服务器在 {self.http_host}:{self.http_port}")
        logger.info(f"[HTTPAdapter] API 前缀: {self.api_prefix}")
        logger.info(f"[HTTPAdapter] 鉴权: {'启用' if self.auth_token else '禁用'}")
        logger.info(f"[HTTPAdapter] CORS 来源: {self.cors_origins}")

        self._running = True

        try:
            # 导入 quart 的运行函数
            import hypercorn.asyncio
            from hypercorn.config import Config

            # 配置 Hypercorn
            config = Config()
            config.bind = [f"{self.http_host}:{self.http_port}"]
            config.use_reloader = False
            # 禁用 Hypercorn 的信号处理，让我们自己处理
            config.signal_handlers = False
            
            await hypercorn.asyncio.serve(self.app, config, shutdown_trigger=self.shutdown_event.wait)

        except Exception as e:
            logger.error(f"[HTTPAdapter] HTTP 服务器启动失败: {e}", exc_info=True)
            self._running = False

    async def terminate(self):
        """终止适配器并清理所有资源"""
        logger.info("[HTTPAdapter] 正在关闭，清理异步任务...")

        # 停止运行标志
        self._running = False
        self.shutdown_event.set()

        # 取消并等待后台任务
        if self._background_tasks:
            for task in list(self._background_tasks):
                task.cancel()

            await asyncio.gather(
                *self._background_tasks,
                return_exceptions=True
            )

            self._background_tasks.clear()

        # 取消所有等待中的响应
        if self.pending_responses:
            for event_id, pending in list(self.pending_responses.items()):
                if not pending.future.done():
                    pending.future.set_exception(
                        asyncio.CancelledError("适配器终止")
                    )

            self.pending_responses.clear()

        # 调用父类终止
        await super().terminate()

        logger.info("[HTTPAdapter] 适配器已安全终止")


