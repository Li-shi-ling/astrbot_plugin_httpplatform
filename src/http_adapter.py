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

from quart import Quart, request, jsonify, websocket as quart_ws, make_response
from quart_cors import cors
from collections.abc import AsyncGenerator

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
from astrbot.api.event import AstrMessageEvent

# 导入常量和数据类
from .constants import HTTP_MESSAGE_TYPE, HTTP_EVENT_TYPE, HTTP_STATUS_CODE, WS_CLOSE_CODE
from .dataclasses import HTTPRequestData, PendingResponse, SessionStats, AdapterStats
from .tool import BMC2Text


# ==================== HTTP 消息事件类 ====================
class HTTPMessageEvent(AstrMessageEvent):
    """HTTP 消息事件基类"""

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data):
        # 调用父类初始化
        super().__init__(message_str, message_obj, platform_meta, session_id)

        # 设置自定义属性
        self._adapter = adapter
        self.event_id = event_id
        self.http_request_data = request_data
        self._raw_headers = request_data.headers

        # 设置额外信息
        self._set_extra_info(request_data)

        # 初始化状态属性
        self.is_wake = True
        self.is_at_or_wake_command = True

    def _set_extra_info(self, request_data: HTTPRequestData):
        """设置额外信息"""
        self.set_extra("event_id", self.event_id)
        self.set_extra("event_type", HTTP_EVENT_TYPE["HTTP_REQUEST"])
        self.set_extra("http_request", True)
        self.set_extra("request_method", request_data.method)
        self.set_extra("request_url", request_data.url)
        self.set_extra("request_headers", dict(request_data.headers))
        self.set_extra("remote_addr", request_data.remote_addr)
        self.set_extra("user_agent", request_data.user_agent)
        self.set_extra("content_type", request_data.content_type)
        self.set_extra("accept", request_data.accept)
        self.set_extra("request_timestamp", request_data.timestamp)
        self.set_extra("data",request_data.data)

    @property
    def adapter(self):
        """获取适配器实例"""
        return self._adapter

    @property
    def headers(self):
        """获取原始请求头"""
        return self._raw_headers

    async def send(self, message_chain: MessageChain):
        """发送响应"""
        raise NotImplementedError("子类必须实现 send 方法")

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ):
        """发送流式消息到消息平台，使用异步生成器"""
        # HTTP 适配器的流式处理
        try:
            async for message_chain in generator:
                # 对于 HTTP 适配器，流式发送实际上就是调用 send 方法
                await self.send(message_chain)
        except Exception as e:
            logger.error(f"[HTTPMessageEvent] 流式发送时出错: {e}")
            raise

class StandardHTTPMessageEvent(HTTPMessageEvent):
    """标准 HTTP 消息事件"""

    async def send(self, message_chain: MessageChain):
        """重写 send 方法，用于返回响应"""
        response_text = str(message_chain)
        if self.event_id in self._adapter.pending_responses:
            pending = self._adapter.pending_responses.pop(self.event_id)
            if not pending.future.done():
                pending.future.set_result(response_text)

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ):
        """发送流式消息到消息平台，使用异步生成器"""
        # 对于标准 HTTP 适配器，流式发送自动转变为普通发送
        try:
            async for message_chain in generator:
                await self.send(message_chain)
        except Exception as e:
            logger.error(f"[StandardHTTPMessageEvent] 流式发送时出错: {e}")
            raise

class StreamHTTPMessageEvent(HTTPMessageEvent):
    """流式 HTTP 消息事件 - 修复版"""

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, queue, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self.queue = queue
        self._message_buffer = []  # 新增：消息缓冲区
        self._is_streaming = False  # 新增：是否正在流式传输
        self._stream_complete = asyncio.Event()  # 新增：流式完成事件
        self.set_extra("event_type", HTTP_EVENT_TYPE["STREAMING"])
        self.set_extra("streaming", True)

    async def send(self, message_chain: MessageChain):
        """发送完整响应 - 这是单条消息的结束"""
        # 如果正在流式传输，先发送流式结束
        if self._is_streaming:
            await self._end_streaming()

        for message in message_chain.chain:
            response_text, text_type = BMC2Text(message)
            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["STREAM"],
                "data": {"chunk": response_text},
                "text_type": text_type
            })
        # 注意：不发送 END，因为可能还有后续消息

    async def _end_streaming(self):
        """结束当前的流式传输"""
        if self._is_streaming:
            self._is_streaming = False
            self._stream_complete.set()

    async def send_streaming(
            self,
            generator: AsyncGenerator[MessageChain, None],
            use_fallback: bool = False,
    ):
        """发送流式消息到消息平台，使用异步生成器"""
        try:
            async for message_chain in generator:
                for message in message_chain.chain:
                    response_text, text_type = BMC2Text(message)
                    await self.queue.put({
                        "type": HTTP_MESSAGE_TYPE["STREAM"],
                        "data": {"chunk": response_text},
                        "text_type": text_type
                    })

            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["END"],
                "data": {}
            })

        except Exception as e:
            logger.error(f"[StreamHTTPMessageEvent] 流式发送时出错: {e}")
            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["ERROR"],
                "data": {"error": str(e)}
            })
            # 即使出错也要发送 END
            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["END"],
                "data": {"error": True}
            })

    def mark_conversation_end(self):
        """标记整个对话结束（由外部调用）"""
        # 结束任何正在进行的流式传输
        asyncio.create_task(self._end_streaming())

        # 发送最终结束事件
        asyncio.create_task(self.queue.put({
            "type": HTTP_MESSAGE_TYPE["END"],
            "data": {}
        }))

class WebSocketMessageEvent(HTTPMessageEvent):
    """WebSocket 消息事件"""

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, websocket, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self.websocket = websocket
        self._message_buffer = []  # 新增：消息缓冲区
        self._is_streaming = False  # 新增：是否正在流式传输
        self._stream_complete = asyncio.Event()  # 新增：流式完成事件
        self.set_extra("event_type", HTTP_EVENT_TYPE["WEBSOCKET"])
        self.set_extra("websocket", True)

    async def send(self, message_chain: MessageChain):
        """发送响应到 WebSocket"""
        response_text = str(message_chain)

        # 如果正在流式传输，先发送流式结束
        if self._is_streaming:
            await self._end_streaming()

        # 发送响应
        await self.websocket.send(json.dumps({
            "type": HTTP_MESSAGE_TYPE["RESPONSE"],
            "event_id": self.event_id,
            "message": response_text,
            "timestamp": time.time()
        }))

        # 完成 future
        if self.event_id in self._adapter.pending_responses:
            pending = self._adapter.pending_responses.pop(self.event_id)
            if not pending.future.done():
                pending.future.set_result(response_text)

    async def _end_streaming(self):
        """结束当前的流式传输"""
        if self._is_streaming:
            self._is_streaming = False
            self._stream_complete.set()

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ):
        """WebSocket 流式发送"""
        try:
            self._is_streaming = True
            self._stream_complete.clear()

            async for message_chain in generator:
                for message in message_chain.chain:
                    response_text, text_type = BMC2Text(message)
                    # 发送流式响应
                    await self.websocket.send(json.dumps({
                        "type": HTTP_MESSAGE_TYPE["STREAM"],
                        "event_id": self.event_id,
                        "chunk": response_text,
                        "text_type": text_type,
                        "timestamp": time.time()
                    }))

            # 发送结束事件
            await self.websocket.send(json.dumps({
                "type": HTTP_MESSAGE_TYPE["END"],
                "event_id": self.event_id,
                "timestamp": time.time()
            }))

            # 结束流式传输
            await self._end_streaming()

        except Exception as e:
            logger.error(f"[WebSocketMessageEvent] 流式发送时出错: {e}")
            # 发送错误消息
            await self.websocket.send(json.dumps({
                "type": HTTP_MESSAGE_TYPE["ERROR"],
                "event_id": self.event_id,
                "message": f"流式发送错误: {str(e)}",
                "timestamp": time.time()
            }))
            # 即使出错也要结束流式传输
            await self._end_streaming()
            raise

    def mark_conversation_end(self):
        """标记整个对话结束（由外部调用）"""
        # 结束任何正在进行的流式传输
        asyncio.create_task(self._end_streaming())

        # 发送最终结束事件
        asyncio.create_task(self.websocket.send(json.dumps({
            "type": HTTP_MESSAGE_TYPE["END"],
            "event_id": self.event_id,
            "timestamp": time.time()
        })))

# ==================== HTTP 会话类 ====================
class HTTPSession:
    """HTTP 会话管理类"""

    def __init__(self, session_id: str, websocket, adapter, client_ip: Optional[str] = None, user_agent: Optional[str] = None):
        self.session_id = session_id
        self.websocket = websocket
        self.adapter = adapter
        self.client_ip = client_ip
        self.user_agent = user_agent
        self.created_at = time.time()
        self.last_active = time.time()
        self.message_count = 0
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None

    def is_active(self) -> bool:
        """检查会话是否活跃"""
        return time.time() - self.last_active < self.adapter.session_timeout

    async def handle_message(self, data: dict):
        """处理 WebSocket 消息"""
        self.last_active = time.time()
        self.message_count += 1

        message_type = data.get('type', HTTP_MESSAGE_TYPE["MESSAGE"])

        if message_type == HTTP_MESSAGE_TYPE["MESSAGE"]:
            await self._handle_message(data)
        elif message_type == HTTP_MESSAGE_TYPE["PING"]:
            await self._handle_ping(data)
        else:
            await self.send_error(f"未知的消息类型: {message_type}")

    async def _handle_message(self, data: dict):
        """处理普通消息"""
        message = data.get('message', '')
        if not message:
            await self.send_error("message 参数是必需的")
            return

        # 更新用户信息
        self.user_id = data.get('user_id', self.user_id or self.session_id)
        self.username = data.get('username', self.username or 'WebSocket用户')

        # 收集请求头信息
        headers = {}
        if hasattr(self.websocket, 'headers'):
            headers = dict(self.websocket.headers)

        request_data = HTTPRequestData(
            method="WEBSOCKET",
            url=f"ws://{self.adapter.http_host}:{self.adapter.http_port}{self.adapter.api_prefix}/ws",
            headers=headers,
            remote_addr=self.client_ip,
            user_agent=self.user_agent
        )

        # 生成事件 ID
        event_id = str(uuid.uuid4())
        future = asyncio.Future()
        self.adapter.pending_responses[event_id] = PendingResponse(
            future=future,
            session_id=self.session_id,
            timeout=data.get('timeout', 30)
        )

        # 创建消息对象
        abm = AstrBotMessage()
        abm.self_id = str(self.adapter.meta().id)
        abm.sender = MessageMember(
            user_id=str(self.user_id),
            nickname=self.username,
        )
        abm.type = MessageType.GROUP_MESSAGE
        abm.session_id = self.session_id
        abm.message_id = data.get('message_id', str(uuid.uuid4().hex))
        abm.message = [Plain(text=message)]
        abm.message_str = message
        abm.raw_message = data
        abm.timestamp = int(time.time())

        # 创建事件
        event = WebSocketMessageEvent(
            message_str=message,
            message_obj=abm,
            platform_meta=self.adapter.meta(),
            session_id=self.session_id,
            adapter=self.adapter,
            websocket=self.websocket,
            event_id=event_id,
            request_data=request_data
        )

        # 设置额外信息
        event.set_extra("client_ip", self.client_ip)
        event.set_extra("original_data", data)

        event.is_wake = True
        event.is_at_or_wake_command = True

        # 提交事件
        self.adapter.commit_event(event)

        # 发送确认
        await self.websocket.send(json.dumps({
            "type": HTTP_MESSAGE_TYPE["ACK"],
            "event_id": event_id,
            "status": "received",
            "timestamp": time.time()
        }))

        logger.debug(f"[HTTPAdapter] WebSocket消息已提交: {event_id}, 会话: {self.session_id}")

    async def _handle_ping(self, data: dict):
        """处理心跳消息"""
        await self.websocket.send(json.dumps({
            "type": HTTP_MESSAGE_TYPE["PONG"],
            "timestamp": time.time(),
            "data": data.get('data')
        }))

    async def send_error(self, error_message: str):
        """发送错误消息"""
        await self.websocket.send(json.dumps({
            "type": HTTP_MESSAGE_TYPE["ERROR"],
            "message": error_message,
            "timestamp": time.time()
        }))

    async def close(self, reason: str = "正常关闭"):
        """关闭会话"""
        if hasattr(self.websocket, 'close'):
            try:
                await self.websocket.close(WS_CLOSE_CODE["NORMAL_CLOSURE"], reason)
            except Exception as e:
                logger.debug(f"[HTTPAdapter] 关闭WebSocket时出错: {e}")
        logger.info(f"[HTTPAdapter] 会话关闭: {self.session_id}, 原因: {reason}")

    def get_stats(self) -> SessionStats:
        """获取会话统计信息"""
        return SessionStats(
            session_id=self.session_id,
            created_at=self.created_at,
            last_active=self.last_active,
            message_count=self.message_count,
            user_id=self.user_id,
            username=self.username,
            client_ip=self.client_ip,
            user_agent=self.user_agent,
            is_active=self.is_active()
        )

# ==================== HTTP 适配器主类 ====================
@register_platform_adapter(
    "http_adapter",
    "HTTP/HTTPS 适配器 - 提供外部 HTTP 接口访问 AstrBot",
    default_config_tmpl={
        "http_host": "0.0.0.0",
        "http_port": 8080,
        "api_prefix": "/api/v1",
        "enable_websocket": True,
        "enable_http_api": True,
        "auth_token": "",
        "cors_origins": "*",
        "max_request_size": 10485760,  # 10MB
        "request_timeout": 30,
        "session_timeout": 3600,  # 会话超时时间(秒)
        "max_sessions": 1000,  # 最大会话数
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
        self.enable_websocket = platform_config.get("enable_websocket", True)
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

        # WebSocket 接口
        if self.enable_websocket:
            @self.app.websocket(f'{self.api_prefix}/ws')
            async def websocket_endpoint():
                """WebSocket 连接端点"""
                await self._handle_websocket_connection()

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
                accept=request_obj.headers.get('Accept'),
                data=data  # 这里传入请求体数据
            )

            # 必需参数检查
            message = data.get('message')
            if not message:
                return jsonify({"error": "message 参数是必需的"}), HTTP_STATUS_CODE["BAD_REQUEST"]

            # 获取会话ID或创建新的
            session_id = data.get('session_id', str(uuid.uuid4()))
            user_id = data.get('user_id', 'external_user')
            username = data.get('username', '外部用户')

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
                nickname=username,
            )
            abm.type = MessageType.GROUP_MESSAGE
            abm.session_id = session_id
            abm.message_id = data.get('message_id', str(uuid.uuid4().hex))
            abm.message = [Plain(text=message)]
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
            event.set_extra("original_data", data)

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

            session_id = data.get('session_id', str(uuid.uuid4()))
            user_id = data.get('user_id', 'external_user')
            username = data.get('username', '外部用户')

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
                abm.message = [Plain(text=message)]
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
                    yield f"event: {HTTP_MESSAGE_TYPE['END']}\ndata: {{'reason': 'cancelled'}}\n\n"
                except Exception as e:
                    logger.error(f"[HTTPAdapter] 生成SSE时出错: {e}", exc_info=True)
                    yield f"event: {HTTP_MESSAGE_TYPE['ERROR']}\ndata: {{'error': str(e), 'event_id': event_id}}\n\n"

                finally:
                    # 清理资源
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

    async def _handle_websocket_connection(self):
        """处理 WebSocket 连接"""
        ws = quart_ws

        # 获取客户端信息
        client_ip = ws.remote_addr
        user_agent = ws.headers.get('User-Agent')

        # 鉴权
        if self.auth_token:
            token = ws.args.get('token') or ws.headers.get('Authorization', '').replace('Bearer ', '')
            if token != self.auth_token:
                await ws.close(WS_CLOSE_CODE["POLICY_VIOLATION"], "未授权访问")
                return

        session_id = str(uuid.uuid4())

        # 创建会话
        session = HTTPSession(
            session_id=session_id,
            websocket=ws,
            adapter=self,
            client_ip=client_ip,
            user_agent=user_agent
        )

        # 检查会话数量限制
        if len(self.sessions) >= self.max_sessions:
            oldest_session_id = min(self.sessions.keys(), key=lambda k: self.sessions[k].last_active)
            oldest_session = self.sessions.pop(oldest_session_id)
            await oldest_session.close("会话数量超限，关闭最旧会话")

        self.sessions[session_id] = session

        logger.info(f"[HTTPAdapter] WebSocket 连接建立: {session_id}, IP: {client_ip}")

        try:
            # 发送连接成功消息
            await ws.send(json.dumps({
                "type": HTTP_MESSAGE_TYPE["CONNECTED"],
                "session_id": session_id,
                "timestamp": time.time()
            }))

            # 处理消息
            while True:
                data = await ws.receive()
                if data is None:
                    break

                try:
                    message_data = json.loads(data)
                    await session.handle_message(message_data)
                except json.JSONDecodeError:
                    await session.send_error("无效的 JSON 数据")
                except Exception as e:
                    logger.error(f"[HTTPAdapter] 处理WebSocket消息时出错: {e}")
                    await session.send_error(f"处理消息时出错: {str(e)}")

        except Exception as e:
            if "1000" not in str(e) and "1001" not in str(e):  # 忽略正常关闭
                logger.error(f"[HTTPAdapter] WebSocket连接错误: {e}")
        finally:
            if session_id in self.sessions:
                del self.sessions[session_id]
            logger.info(f"[HTTPAdapter] WebSocket连接关闭: {session_id}")

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
        logger.info(f"[HTTPAdapter] WebSocket: {'启用' if self.enable_websocket else '禁用'}")
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

            # 启动服务器
            await hypercorn.asyncio.serve(self.app, config)

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
        """终止适配器"""
        logger.info("[HTTPAdapter] 终止适配器...")
        self._running = False

        # 取消清理任务
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 关闭所有 WebSocket 会话
        close_tasks = []
        for session_id, session in list(self.sessions.items()):
            close_tasks.append(session.close("适配器终止"))

        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        # 取消所有等待的响应
        for event_id, pending in list(self.pending_responses.items()):
            if not pending.future.done():
                pending.future.set_exception(asyncio.CancelledError("适配器终止"))

        self.sessions.clear()
        self.pending_responses.clear()

        logger.info("[HTTPAdapter] 适配器已终止")
