"""
简单 HTTP 适配器 - 提供基本的 HTTP 接口
"""

import asyncio
import time
import uuid

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

# 导入常量
from .constants import HTTP_EVENT_TYPE, HTTP_STATUS_CODE

@register_platform_adapter(
    "simple_http",
    "简单 HTTP 适配器",
    default_config_tmpl={
        "port": 8080,
        "host": "0.0.0.0",
        "auth_token": "",
    },
)
class SimpleHTTPAdapter(Platform):
    """简单的 HTTP 适配器"""

    def __init__(self, platform_config: dict, platform_settings: dict, event_queue: asyncio.Queue):
        super().__init__(platform_config, event_queue)

        self.port = int(platform_config.get("port", 8080))
        self.host = platform_config.get("host", "0.0.0.0")
        self.auth_token = platform_config.get("auth_token", "")

        # 响应映射
        self.pending_responses = {}

        # 平台元数据
        self._metadata = PlatformMetadata(
            name="simple_http",
            description="简单 HTTP 适配器",
            id=platform_config.get("id", "simple_http_default"),
        )

        # 启动简单的 HTTP 服务器
        self._server = None

    def meta(self) -> PlatformMetadata:
        return self._metadata

    async def send_by_session(self, session, message_chain):
        pass

    def run(self):
        return self._start_server()

    async def _start_server(self):
        """启动一个简单的 HTTP 服务器"""
        try:
            from aiohttp import web

            app = web.Application()

            # 健康检查
            async def health(request):
                return web.json_response({"status": "ok", "service": "astrbot"})

            # 发送消息
            async def send_message(request):
                # 鉴权
                if self.auth_token:
                    auth = request.headers.get('Authorization', '')
                    if not auth.startswith('Bearer ') or auth[7:] != self.auth_token:
                        return web.json_response({"error": "未授权"}, status=HTTP_STATUS_CODE["UNAUTHORIZED"])

                try:
                    data = await request.json()
                    message = data.get('message', '')
                    session_id = data.get('session_id', str(uuid.uuid4()))

                    if not message:
                        return web.json_response({"error": "message 参数必需"}, status=HTTP_STATUS_CODE["BAD_REQUEST"])

                    # 收集请求头信息
                    headers = dict(request.headers)

                    # 创建事件
                    event_id = str(uuid.uuid4())
                    future = asyncio.Future()
                    self.pending_responses[event_id] = future

                    # 构建消息
                    abm = AstrBotMessage()
                    abm.self_id = self._metadata.id
                    abm.sender = MessageMember(
                        user_id=data.get('user_id', 'http_user'),
                        nickname=data.get('username', 'HTTP用户'),
                    )
                    abm.type = MessageType.GROUP_MESSAGE
                    abm.session_id = session_id
                    abm.message_id = str(uuid.uuid4().hex)
                    abm.message = [Plain(text=message)]
                    abm.message_str = message
                    abm.raw_message = data
                    abm.timestamp = int(time.time())

                    # 创建自定义事件
                    from astrbot.api.event import AstrMessageEvent

                    class SimpleHTTPEvent(AstrMessageEvent):
                        def __init__(self, *args, event_id, adapter, headers, **kwargs):
                            super().__init__(*args, **kwargs)
                            self.event_id = event_id
                            self._adapter = adapter
                            self._raw_headers = headers

                        @property
                        def adapter(self):
                            return self._adapter

                        @property
                        def headers(self):
                            """获取原始请求头"""
                            return self._raw_headers

                        async def send(self, message_chain: MessageChain):
                            response = str(message_chain)
                            if self.event_id in self._adapter.pending_responses:
                                future = self._adapter.pending_responses.pop(self.event_id)
                                if not future.done():
                                    future.set_result(response)

                    event = SimpleHTTPEvent(
                        message_str=message,
                        message_obj=abm,
                        platform_meta=self._metadata,
                        session_id=session_id,
                        event_id=event_id,
                        adapter=self,
                        headers=headers
                    )

                    # 设置额外信息
                    event.set_extra("event_id", event_id)
                    event.set_extra("event_type", HTTP_EVENT_TYPE["HTTP_REQUEST"])
                    event.set_extra("http_request", True)
                    event.set_extra("request_method", request.method)
                    event.set_extra("request_url", str(request.url))
                    event.set_extra("request_headers", headers)
                    event.set_extra("remote_addr", request.remote)
                    event.set_extra("user_agent", request.headers.get('User-Agent'))
                    event.set_extra("content_type", request.content_type)
                    event.set_extra("accept", request.headers.get('Accept'))
                    event.set_extra("original_data", data)

                    event.is_wake = True
                    event.is_at_or_wake_command = True

                    # 提交事件
                    self.commit_event(event)

                    # 等待响应
                    try:
                        response = await asyncio.wait_for(future, timeout=30)
                        return web.json_response({
                            "success": True,
                            "response": response,
                            "event_id": event_id
                        })
                    except asyncio.TimeoutError:
                        if event_id in self.pending_responses:
                            del self.pending_responses[event_id]
                        return web.json_response({"error": "请求超时"}, status=HTTP_STATUS_CODE["TIMEOUT"])

                except Exception as e:
                    logger.error(f"[SimpleHTTP] 处理请求出错: {e}")
                    return web.json_response({"error": str(e)}, status=HTTP_STATUS_CODE["INTERNAL_ERROR"])

            # 注册路由
            app.router.add_get('/health', health)
            app.router.add_post('/message', send_message)

            # 启动服务器
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, self.host, self.port)
            self._server = site

            logger.info(f"[SimpleHTTP] HTTP 服务器启动在 {self.host}:{self.port}")
            await site.start()

            # 保持运行
            while True:
                await asyncio.sleep(3600)

        except Exception as e:
            logger.error(f"[SimpleHTTP] 服务器启动失败: {e}")

    async def terminate(self):
        """终止适配器"""
        logger.info("[SimpleHTTP] 终止适配器")

        # 清理所有等待的响应
        for event_id, future in list(self.pending_responses.items()):
            if not future.done():
                future.set_exception(asyncio.CancelledError())

        self.pending_responses.clear()

        if self._server:
            await self._server.stop()