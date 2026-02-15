"""
HTTP/HTTPS Platform Adapter for AstrBot

此适配器提供 HTTP/HTTPS 接口，让外部应用可以通过 HTTP 访问 AstrBot。
内部会将 HTTP 请求转换为 WebSocket 通信，并将响应返回给 HTTP 客户端。
"""

import asyncio
import json
import time
import uuid
from typing import Any, Dict, List, Optional
from collections.abc import Coroutine

from quart import Quart, request, jsonify, make_response
from quart_cors import cors

from astrbot import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
from astrbot.core.platform.astr_message_event import MessageSesion

# 导入常量和数据类
from .constants import HTTP_MESSAGE_TYPE, HTTP_EVENT_TYPE, HTTP_STATUS_CODE
from .dataclasses import HTTPRequestData, PendingResponse, SessionStats, AdapterStats
from .httpmessageevent import StandardHTTPMessageEvent, HTTPMessageEvent, StreamHTTPMessageEvent
from .httpsession import HTTPSession
from .tool import Json2BMCChain

# ==================== HTTP 适配器主类 ====================
@register_platform_adapter(
    "http_adapter",  # 适配器名称
    "HTTP/HTTPS 适配器 - 提供外部 HTTP 接口访问 AstrBot",  # 描述
    default_config_tmpl={
        "http_host": "0.0.0.0",
        "http_port": 8080,
        "api_prefix": "/api/v1",
        "enable_http_api": True,
        "auth_token": "",
        "cors_origins": "*",
        "max_request_size": 10485760,  # 10MB
        "request_timeout": 30,
        "session_timeout": 3600,  # 会话超时时间(秒)
        "max_sessions": 1000,  # 最大会话数
    },
    i18n_resources={
        "zh-CN": {
            "http_host": {
                "description": "HTTP 监听主机",
                "hint": "HTTP 服务器监听的主机地址，0.0.0.0 表示所有网络接口",
            },
            "http_port": {
                "description": "HTTP 监听端口",
                "hint": "HTTP 服务器监听的端口号",
            },
            "api_prefix": {
                "description": "API 路径前缀",
                "hint": "所有 API 接口的 URL 前缀",
            },
            "enable_http_api": {
                "description": "启用 HTTP API",
                "hint": "是否启动 HTTP API 服务",
            },
            "auth_token": {
                "description": "认证令牌",
                "hint": "API 访问认证令牌，留空表示不启用认证",
            },
            "cors_origins": {
                "description": "CORS 允许的源",
                "hint": "跨域请求允许的来源，多个用逗号分隔，* 表示全部允许",
            },
            "max_request_size": {
                "description": "最大请求大小 (bytes)",
                "hint": "允许的最大请求体大小，单位字节",
            },
            "request_timeout": {
                "description": "请求超时时间 (s)",
                "hint": "HTTP 请求处理超时时间，单位秒",
            },
            "session_timeout": {
                "description": "会话超时时间 (s)",
                "hint": "会话保持的最长时间，超过此时间未活动的会话将被清理",
            },
            "max_sessions": {
                "description": "最大会话数",
                "hint": "同时保持的最大会话数量",
            },
        },
        "en-US": {
            "http_host": {
                "description": "HTTP listen host",
                "hint": "HTTP server listen host, 0.0.0.0 for all interfaces",
            },
            "http_port": {
                "description": "HTTP listen port",
                "hint": "HTTP server listen port",
            },
            "api_prefix": {
                "description": "API path prefix",
                "hint": "URL prefix for all API endpoints",
            },
            "enable_http_api": {
                "description": "Enable HTTP API",
                "hint": "Whether to start the HTTP API service",
            },
            "auth_token": {
                "description": "Auth token",
                "hint": "API access authentication token, leave empty to disable",
            },
            "cors_origins": {
                "description": "CORS allowed origins",
                "hint": "Allowed origins for CORS, comma separated, * for all",
            },
            "max_request_size": {
                "description": "Max request size (bytes)",
                "hint": "Maximum allowed request body size in bytes",
            },
            "request_timeout": {
                "description": "Request timeout (s)",
                "hint": "HTTP request processing timeout in seconds",
            },
            "session_timeout": {
                "description": "Session timeout (s)",
                "hint": "Maximum session idle time before cleanup",
            },
            "max_sessions": {
                "description": "Max sessions",
                "hint": "Maximum number of concurrent sessions",
            },
        },
    },
    config_metadata={
        "http_host": {
            "description": "HTTP 监听主机",
            "type": "string",
            "hint": "HTTP 服务器监听的主机地址，0.0.0.0 表示所有网络接口",
        },
        "http_port": {
            "description": "HTTP 监听端口",
            "type": "int",
            "hint": "HTTP 服务器监听的端口号",
        },
        "api_prefix": {
            "description": "API 路径前缀",
            "type": "string",
            "hint": "所有 API 接口的 URL 前缀",
        },
        "enable_http_api": {
            "description": "启用 HTTP API",
            "type": "bool",
            "hint": "是否启动 HTTP API 服务",
        },
        "auth_token": {
            "description": "认证令牌",
            "type": "string",
            "hint": "API 访问认证令牌，留空表示不启用认证",
        },
        "cors_origins": {
            "description": "CORS 允许的源",
            "type": "string",
            "hint": "跨域请求允许的来源，多个用逗号分隔，* 表示全部允许",
        },
        "max_request_size": {
            "description": "最大请求大小 (bytes)",
            "type": "int",
            "hint": "允许的最大请求体大小，单位字节",
        },
        "request_timeout": {
            "description": "请求超时时间 (s)",
            "type": "int",
            "hint": "HTTP 请求处理超时时间，单位秒",
        },
        "session_timeout": {
            "description": "会话超时时间 (s)",
            "type": "int",
            "hint": "会话保持的最长时间，超过此时间未活动的会话将被清理",
        },
        "max_sessions": {
            "description": "最大会话数",
            "type": "int",
            "hint": "同时保持的最大会话数量",
        },
    },
)
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
        self.cors_origins = platform_config.get("cors_origins", "*").split(",")
        self.session_timeout = int(platform_config.get("session_timeout", 3600))
        self.max_sessions = int(platform_config.get("max_sessions", 1000))

        # 统计信息
        self.total_requests_processed = 0
        self.total_errors = 0

        # 会话管理
        self.sessions: Dict[str, HTTPSession] = {}
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
        self._server_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None

        # 平台元数据
        platform_id = platform_config.get("id", "http_adapter_default")
        self._metadata = PlatformMetadata(
            name="http_adapter",
            description="HTTP/HTTPS 适配器 - 提供外部 HTTP 接口",
            id=platform_id,
            support_streaming_message=True,
            support_proactive_message=True,
        )

        self._background_tasks = set() # 用于追踪任务

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
            response = make_response('')
            response.status_code = HTTP_STATUS_CODE["OK"]

            # quart-cors 会自动处理 CORS 头部，我们只需要返回空响应
            return response

        # 健康检查
        @self.app.route(f'{self.api_prefix}/health', methods=['GET'])
        async def health_check():
            return jsonify({
                "status": "ok",
                "service": "astrbot_http_adapter",
                "timestamp": time.time(),
                "sessions": len(self.sessions),
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

        # 会话管理接口
        @self.app.route(f'{self.api_prefix}/sessions', methods=['GET', 'OPTIONS'])
        async def list_sessions():
            """获取所有活跃会话"""
            if request.method == 'OPTIONS':
                return '', HTTP_STATUS_CODE["OK"]
            return await self._handle_list_sessions(request)

        # 清理会话接口
        @self.app.route(f'{self.api_prefix}/sessions/<session_id>', methods=['DELETE', 'OPTIONS'])
        async def delete_session(session_id):
            """删除指定会话"""
            if request.method == 'OPTIONS':
                return '', HTTP_STATUS_CODE["OK"]
            return await self._handle_delete_session(request, session_id)

        # 统计信息接口
        @self.app.route(f'{self.api_prefix}/stats', methods=['GET', 'OPTIONS'])
        async def get_stats():
            """获取统计信息"""
            if request.method == 'OPTIONS':
                return '', HTTP_STATUS_CODE["OK"]
            return await self._handle_get_stats(request)

    async def _handle_http_message(self, request_obj) -> Any:
        """处理 HTTP 消息请求"""
        # 鉴权
        auth_result = await self._check_auth(request_obj)
        if auth_result is not None:
            return auth_result

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
            if isinstance(message, List):
                messages = Json2BMCChain(message)
            # 获取会话ID或创建新的
            platform = data.get('platform', "")
            user_id = data.get('user_id', '0')
            nickname = data.get('nickname', '外部用户')
            session_id = f"{platform}_{user_id}"

            # 创建事件并提交
            event_id = str(uuid.uuid4())
            future = asyncio.Future()
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
            abm.message_str = message
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
            logger.error(f"[HTTPAdapter] 处理HTTP请求时出错: {e}", exc_info=True)
            return jsonify({"error": f"内部服务器错误: {str(e)}"}), HTTP_STATUS_CODE["INTERNAL_ERROR"]

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
            messages = []
            if isinstance(message, List):
                messages = Json2BMCChain(message)
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
                if messages is None:
                    abm.message = [Plain(text=message)]
                else:
                    abm.message = messages
                abm.message_str = message
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
                            yield f"event: {HTTP_MESSAGE_TYPE['TIMEOUT']}\ndata: {{'reason': 'total_timeout', 'duration': current_time - start_time}}\n\n"
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
                                yield f"event: {HTTP_MESSAGE_TYPE['END']}\ndata: {{'reason': 'normal_end'}}\n\n"
                                received_end_event = True
                                break

                            # 处理事件
                            event_type = item.get('type')
                            event_data = item.get('data', {})

                            # 更新最后活动时间
                            last_activity_time = time.time()

                            # 发送事件
                            yield f"event: {event_type}\ndata: {json.dumps(event_data, ensure_ascii=False)}\n\n"

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

    async def _handle_list_sessions(self, request_obj) -> Any:
        """处理获取会话列表请求"""
        # 鉴权
        auth_result = await self._check_auth(request_obj)
        if auth_result is not None:
            return auth_result

        sessions = []
        for session_id, session in self.sessions.items():
            sessions.append(session.get_stats().__dict__)

        return jsonify({
            "sessions": sessions,
            "total": len(sessions),
            "timestamp": time.time()
        })

    async def _handle_delete_session(self, request_obj, session_id: str) -> Any:
        """处理删除会话请求"""
        # 鉴权
        auth_result = await self._check_auth(request_obj)
        if auth_result is not None:
            return auth_result

        if session_id in self.sessions:
            session = self.sessions.pop(session_id)
            await session.close("管理员删除")
            return jsonify({
                "success": True,
                "message": f"会话 {session_id} 已删除",
                "session_id": session_id
            })
        else:
            return jsonify({
                "error": f"会话 {session_id} 不存在"
            }), HTTP_STATUS_CODE["NOT_FOUND"]

    async def _handle_get_stats(self, request_obj) -> Any:
        """处理获取统计信息请求"""
        # 鉴权
        auth_result = await self._check_auth(request_obj)
        if auth_result is not None:
            return auth_result

        # 清理过期的待处理响应
        expired_responses = self._cleanup_expired_responses()

        # 清理超时会话
        expired_sessions = self._cleanup_expired_sessions()

        # 构建统计信息
        stats = AdapterStats(
            timestamp=time.time(),
            sessions_active=len(self.sessions),
            sessions_max_limit=self.max_sessions,
            sessions_expired=len(expired_sessions),
            pending_responses_active=len(self.pending_responses),
            pending_responses_expired=len(expired_responses),
            total_requests_processed=self.total_requests_processed,
            total_errors=self.total_errors
        )

        return jsonify(stats.__dict__)

    def _cleanup_expired_responses(self) -> List[str]:
        """清理过期的待处理响应"""
        expired_responses = []
        current_time = time.time()

        for event_id, pending in list(self.pending_responses.items()):
            if current_time - pending.created_at > pending.timeout:
                expired_responses.append(event_id)
                if not pending.future.done():
                    pending.future.set_exception(asyncio.TimeoutError("响应超时"))

        for event_id in expired_responses:
            self.pending_responses.pop(event_id, None)

        return expired_responses

    def _cleanup_expired_sessions(self) -> List[str]:
        """清理超时会话"""
        expired_sessions = []
        current_time = time.time()

        for session_id, session in list(self.sessions.items()):
            if current_time - session.last_active > self.session_timeout:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            session = self.sessions.pop(session_id)
            asyncio.create_task(session.close("会话超时自动清理"))

        return expired_sessions

    async def _check_auth(self, request_obj) -> Optional[Any]:
        """检查鉴权"""
        if not self.auth_token:
            return None

        auth_header = request_obj.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({"error": "未授权访问"}), HTTP_STATUS_CODE["UNAUTHORIZED"]

        token = auth_header[7:]
        if token != self.auth_token:
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

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        try:
            # 导入 quart 的运行函数
            import hypercorn.asyncio
            from hypercorn.config import Config

            # 配置 Hypercorn
            config = Config()
            config.bind = [f"{self.http_host}:{self.http_port}"]
            config.use_reloader = False

            # 使用任务包装服务器启动，以便能够响应信号
            server_task = asyncio.create_task(hypercorn.asyncio.serve(self.app, config))
            
            # 等待服务器任务完成或被取消
            await server_task

        except KeyboardInterrupt:
            # 捕获 Ctrl+C 信号
            logger.info("[HTTPAdapter] 收到退出信号，正在停止服务器...")
            self._running = False
            # 取消服务器任务
            if 'server_task' in locals():
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
        except Exception as e:
            logger.error(f"[HTTPAdapter] HTTP 服务器启动失败: {e}", exc_info=True)
            self._running = False
        finally:
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            # 确保服务器任务被取消
            if 'server_task' in locals():
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass

    async def _cleanup_loop(self):
        """清理循环，定期清理过期资源"""
        while self._running:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次

                # 清理过期资源
                expired_responses = self._cleanup_expired_responses()
                expired_sessions = self._cleanup_expired_sessions()

                if expired_sessions or expired_responses:
                    logger.debug(f"[HTTPAdapter] 清理完成: {len(expired_sessions)} 会话, {len(expired_responses)} 响应")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[HTTPAdapter] 清理循环出错: {e}")

    async def terminate(self):
        """终止适配器并清理所有挂起任务"""
        logger.info("[HTTPAdapter] 正在关闭，清理异步任务...")
        self._running = False

        # 清理后台任务，防止 "Task was destroyed but it is pending"
        if self._background_tasks:
            for task in list(self._background_tasks):
                task.cancel()

            # 等待任务取消完成，不抛出异常
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # 清理未完成的 Future
        for event_id in list(self.pending_responses.keys()):
            pending = self.pending_responses.pop(event_id, None)
            if pending and not pending.future.done():
                pending.future.set_exception(asyncio.CancelledError())

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 取消所有等待的响应
        for event_id, pending in list(self.pending_responses.items()):
            if not pending.future.done():
                pending.future.set_exception(asyncio.CancelledError("适配器终止"))

        self.sessions.clear()
        self.pending_responses.clear()

        logger.info("[HTTPAdapter] 适配器已终止")
