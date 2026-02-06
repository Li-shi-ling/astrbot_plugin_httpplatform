# 导入异步IO模块
import asyncio
# 导入JSON处理模块
import json
# 导入随机数模块
import random
# 导入时间模块
import time
# 导入UUID生成模块
import uuid
# 导入协程类型
from collections.abc import Coroutine
# 导入类型注解
from typing import Any, Dict, List, Optional

# 导入aiohttp库，用于HTTP和WebSocket客户端
import aiohttp
# 导入aiohttp的web模块，用于HTTP和WebSocket服务器
from aiohttp import web

# 导入日志模块
from astrbot import logger
# 导入消息链类
from astrbot.api.event import MessageChain
# 导入纯文本消息组件
from astrbot.api.message_components import Plain
# 导入平台相关类
from astrbot.api.platform import (
    AstrBotMessage,      # 机器人消息类
    MessageMember,       # 消息成员类
    MessageType,         # 消息类型枚举
    Platform,            # 平台基类
    PlatformMetadata,    # 平台元数据类
    register_platform_adapter,  # 平台适配器注册装饰器
)
# 导入消息会话类
from astrbot.core.platform.astr_message_event import MessageSesion

# 导入HTTP消息事件类
from .event import HttpMessageEvent


# 注册HTTP平台适配器
@register_platform_adapter(
    "httpplatform",  # 平台名称
    "HTTP 适配器平台 - 支持 WebSocket 到 HTTP 的转换",  # 平台描述
    default_config_tmpl={  # 默认配置模板
        "http_port": 8080,  # HTTP服务器端口
        "ws_port": 8081,    # WebSocket服务器端口
        "api_base": "http://localhost:8080",  # API基础URL
        "ws_url": "ws://localhost:8081",      # WebSocket URL
        "token": "",  # 认证令牌
    },
)
class HttpPlatformAdapter(Platform):
    """HTTP平台适配器实现，支持WebSocket到HTTP的转换"""

    def __init__(
        self,
        platform_config: dict,  # 平台配置字典
        platform_settings: dict,  # 平台设置字典
        event_queue: asyncio.Queue,  # 事件队列
    ) -> None:
        # 调用父类构造函数
        super().__init__(platform_config, event_queue)

        # 保存平台设置
        self.settings = platform_settings
        # 获取HTTP服务器端口，默认8080
        self.http_port = platform_config.get("http_port", 8080)
        # 获取WebSocket服务器端口，默认8081
        self.ws_port = platform_config.get("ws_port", 8081)
        # 获取API基础URL，默认http://localhost:8080
        self.api_base = platform_config.get("api_base", f"http://localhost:{self.http_port}")
        # 获取WebSocket URL，默认ws://localhost:8081
        self.ws_url = platform_config.get("ws_url", f"ws://localhost:{self.ws_port}")
        # 获取认证令牌，默认空字符串
        self.token = platform_config.get("token", "")

        # 从platform_config获取id，是该适配器实例的唯一标识
        platform_id = platform_config.get("id", "httpplatform_default")
        # 创建平台元数据
        self._metadata = PlatformMetadata(
            name="httpplatform",  # 平台名称
            description="HTTP 适配器平台",  # 平台描述
            id=platform_id,  # 平台ID
        )

        # WebSocket服务器状态
        self._ws_server: web.TCPSite | None = None  # WebSocket服务器实例
        self._ws_app: web.Application | None = None  # WebSocket应用实例
        self._ws_connections: List[web.WebSocketResponse] = []  # WebSocket连接列表

        # HTTP服务器状态
        self._http_server: web.TCPSite | None = None  # HTTP服务器实例
        self._http_app: web.Application | None = None  # HTTP应用实例

        # 机器人用户信息
        self.bot_user_id: str = str(uuid.uuid4())  # 生成唯一的机器人用户ID

        # 运行中的任务列表
        self._tasks: list[asyncio.Task] = []  # 存储异步任务

    def meta(self) -> PlatformMetadata:
        """获取平台元数据"""
        return self._metadata

    async def send_by_session(
        self,
        session: MessageSesion,  # 消息会话
        message_chain: MessageChain,  # 消息链
    ):
        """通过会话发送消息"""
        # 调用父类方法
        await super().send_by_session(session, message_chain)

    def run(self) -> Coroutine[Any, Any, None]:
        """适配器主入口点"""
        return self._run()

    async def _run(self):
        """运行适配器，启动WebSocket和HTTP服务器"""
        # 记录启动信息
        logger.info("[HTTP Platform] Starting HTTP platform adapter...")

        # 启动WebSocket服务器任务
        ws_task = asyncio.create_task(self._start_ws_server())
        # 将任务添加到任务列表
        self._tasks.append(ws_task)

        # 启动HTTP服务器任务
        http_task = asyncio.create_task(self._start_http_server())
        # 将任务添加到任务列表
        self._tasks.append(http_task)

        try:
            # 等待所有任务完成
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            # 捕获任务取消异常
            logger.info("[HTTP Platform] Adapter tasks cancelled")

    async def terminate(self):
        """终止适配器"""
        # 记录终止信息
        logger.info("[HTTP Platform] Terminating adapter...")

        # 取消所有运行中的任务
        for task in self._tasks:
            if not task.done():
                task.cancel()

        # 关闭WebSocket服务器
        if self._ws_server:
            await self._ws_server.stop()

        # 关闭HTTP服务器
        if self._http_server:
            await self._http_server.stop()

        # 关闭所有WebSocket连接
        for ws in self._ws_connections:
            if not ws.closed:
                await ws.close()

    # ==================== WebSocket服务器 ====================

    async def _start_ws_server(self):
        """启动WebSocket服务器"""
        # 创建web应用
        app = web.Application()
        # 添加路由，将/ws路径映射到处理函数
        app.add_routes([
            web.get('/ws', self._handle_ws_connection)
        ])

        # 创建应用运行器
        runner = web.AppRunner(app)
        # 设置运行器
        await runner.setup()
        # 创建TCP站点，监听0.0.0.0和配置的WebSocket端口
        site = web.TCPSite(runner, '0.0.0.0', self.ws_port)
        # 保存服务器实例
        self._ws_server = site
        # 保存应用实例
        self._ws_app = app

        # 记录启动信息
        logger.info(f"[HTTP Platform] WebSocket server starting on port {self.ws_port}")
        # 启动服务器
        await site.start()
        # 记录启动成功信息
        logger.info(f"[HTTP Platform] WebSocket server started on ws://localhost:{self.ws_port}/ws")

        # 保持服务器运行
        while True:
            await asyncio.sleep(3600)

    async def _handle_ws_connection(self, request):
        """处理WebSocket连接"""
        # 创建WebSocket响应对象
        ws = web.WebSocketResponse()
        # 准备WebSocket连接
        await ws.prepare(request)

        # 将连接添加到连接列表
        self._ws_connections.append(ws)
        # 记录新连接信息
        logger.info(f"[HTTP Platform] New WebSocket connection established")

        try:
            # 异步迭代接收消息
            async for msg in ws:
                # 处理文本消息
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(ws, msg.data)
                # 处理错误消息
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"[HTTP Platform] WebSocket error: {ws.exception()}")
        finally:
            # 确保连接被移除
            if ws in self._ws_connections:
                self._ws_connections.remove(ws)
            # 记录连接关闭信息
            logger.info(f"[HTTP Platform] WebSocket connection closed")

    async def _handle_ws_message(self, ws: web.WebSocketResponse, message_data: str):
        """处理接收到的WebSocket消息"""
        try:
            # 解析JSON消息
            data = json.loads(message_data)
            # 获取消息类型
            msg_type = data.get("type")
            # 记录接收到的消息类型
            logger.debug(f"[HTTP Platform] Received WS message: {msg_type}")

            # 处理HTTP请求消息
            if msg_type == "http_request":
                await self._handle_http_request_via_ws(ws, data)
            # 处理ping消息
            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})
        except json.JSONDecodeError as e:
            # 处理JSON解析错误
            logger.error(f"[HTTP Platform] Invalid JSON in WebSocket message: {e}")
            await ws.send_json({"type": "error", "error": "Invalid JSON"})
        except Exception as e:
            # 处理其他错误
            logger.error(f"[HTTP Platform] Error handling WebSocket message: {e}")
            await ws.send_json({"type": "error", "error": str(e)})

    async def _handle_http_request_via_ws(self, ws: web.WebSocketResponse, data: Dict):
        """处理通过WebSocket接收的HTTP请求"""
        # 获取请求ID，默认生成新的UUID
        request_id = data.get("request_id", str(uuid.uuid4()))
        # 获取HTTP方法，默认GET
        method = data.get("method", "GET")
        # 获取请求路径，默认/
        path = data.get("path", "/")
        # 获取请求头，默认空字典
        headers = data.get("headers", {})
        # 获取请求体，默认空字典
        body = data.get("body", {})

        # 记录接收到的HTTP请求
        logger.info(f"[HTTP Platform] Received HTTP request via WS: {method} {path}")

        # 将WebSocket消息转换为HTTP请求
        try:
            # 创建HTTP客户端会话
            async with aiohttp.ClientSession() as session:
                # 构建完整的URL
                url = f"{self.api_base}{path}"
                # 记录发送HTTP请求的信息
                logger.debug(f"[HTTP Platform] Sending HTTP request to: {url}")

                # 处理不同的HTTP方法
                if method == "GET":
                    # 发送GET请求
                    async with session.get(url, headers=headers, params=body) as response:
                        # 解析响应数据
                        response_data = await response.json()
                        # 获取响应状态码
                        status = response.status
                elif method == "POST":
                    # 发送POST请求
                    async with session.post(url, headers=headers, json=body) as response:
                        # 解析响应数据
                        response_data = await response.json()
                        # 获取响应状态码
                        status = response.status
                elif method == "PUT":
                    # 发送PUT请求
                    async with session.put(url, headers=headers, json=body) as response:
                        # 解析响应数据
                        response_data = await response.json()
                        # 获取响应状态码
                        status = response.status
                elif method == "DELETE":
                    # 发送DELETE请求
                    async with session.delete(url, headers=headers) as response:
                        # 解析响应数据
                        response_data = await response.json()
                        # 获取响应状态码
                        status = response.status
                else:
                    # 处理不支持的HTTP方法
                    response_data = {"error": "Method not allowed"}
                    status = 405

                # 将HTTP响应通过WebSocket发送回去
                await ws.send_json({
                    "type": "http_response",  # 消息类型
                    "request_id": request_id,  # 请求ID
                    "status": status,  # 响应状态码
                    "headers": dict(response.headers),  # 响应头
                    "body": response_data  # 响应体
                })
                # 记录发送HTTP响应的信息
                logger.info(f"[HTTP Platform] Sent HTTP response via WS: {status} {path}")

        except Exception as e:
            # 处理错误
            logger.error(f"[HTTP Platform] Error processing HTTP request: {e}")
            # 发送错误响应
            await ws.send_json({
                "type": "http_response",
                "request_id": request_id,
                "status": 500,
                "headers": {},
                "body": {"error": str(e)}
            })

    # ==================== HTTP服务器 ====================

    async def _start_http_server(self):
        """启动HTTP服务器"""
        # 创建web应用
        app = web.Application()
        # 添加路由，处理不同HTTP方法的请求
        app.add_routes([
            web.get('/{tail:.*}', self._handle_http_get),      # 处理GET请求
            web.post('/{tail:.*}', self._handle_http_post),    # 处理POST请求
            web.put('/{tail:.*}', self._handle_http_put),      # 处理PUT请求
            web.delete('/{tail:.*}', self._handle_http_delete),  # 处理DELETE请求
        ])

        # 创建应用运行器
        runner = web.AppRunner(app)
        # 设置运行器
        await runner.setup()
        # 创建TCP站点，监听0.0.0.0和配置的HTTP端口
        site = web.TCPSite(runner, '0.0.0.0', self.http_port)
        # 保存服务器实例
        self._http_server = site
        # 保存应用实例
        self._http_app = app

        # 记录启动信息
        logger.info(f"[HTTP Platform] HTTP server starting on port {self.http_port}")
        # 启动服务器
        await site.start()
        # 记录启动成功信息
        logger.info(f"[HTTP Platform] HTTP server started on http://localhost:{self.http_port}")

        # 保持服务器运行
        while True:
            await asyncio.sleep(3600)

    async def _handle_http_get(self, request):
        """处理HTTP GET请求"""
        return await self._handle_http_request(request, "GET")

    async def _handle_http_post(self, request):
        """处理HTTP POST请求"""
        return await self._handle_http_request(request, "POST")

    async def _handle_http_put(self, request):
        """处理HTTP PUT请求"""
        return await self._handle_http_request(request, "PUT")

    async def _handle_http_delete(self, request):
        """处理HTTP DELETE请求"""
        return await self._handle_http_request(request, "DELETE")

    async def _handle_http_request(self, request, method):
        """处理HTTP请求"""
        # 获取请求路径
        path = request.path
        # 获取请求头
        headers = dict(request.headers)

        try:
            # 解析请求体
            body = await request.json()
        except json.JSONDecodeError:
            # 如果解析失败，使用空字典
            body = {}

        # 记录接收到的HTTP请求
        logger.info(f"[HTTP Platform] Received HTTP request: {method} {path}")

        # 为机器人创建消息事件
        formatted_message = (
            f"[HTTP Request] {method} {path}\n"  
            f"Headers: {json.dumps(headers, indent=2)}\n"  
            f"Body: {json.dumps(body, indent=2)}"
        )

        # 创建机器人消息对象
        abm = AstrBotMessage()
        # 设置机器人ID
        abm.self_id = self.bot_user_id
        # 设置发送者信息
        abm.sender = MessageMember(
            user_id="http_client",  # 发送者ID
            nickname="HTTP Client",  # 发送者昵称
        )
        # 设置消息类型为群组消息
        abm.type = MessageType.GROUP_MESSAGE
        # 设置会话ID
        abm.session_id = "http_platform_session"
        # 设置消息ID
        abm.message_id = str(uuid.uuid4())
        # 设置消息内容
        abm.message = [Plain(text=formatted_message)]
        # 设置消息字符串
        abm.message_str = formatted_message
        # 设置原始消息
        abm.raw_message = {
            "method": method,
            "path": path,
            "headers": headers,
            "body": body
        }
        # 设置时间戳
        abm.timestamp = int(time.time())

        # 创建HTTP消息事件
        event = HttpMessageEvent(
            message_str=formatted_message,
            message_obj=abm,
            platform_meta=self._metadata,
            session_id="http_platform_session",
            adapter=self,
        )

        # 设置额外信息
        event.set_extra("method", method)
        event.set_extra("path", path)
        event.set_extra("headers", headers)
        event.set_extra("body", body)

        # 设置为唤醒事件
        event.is_wake = True
        # 设置为@或唤醒命令
        event.is_at_or_wake_command = True

        # 提交事件到队列
        self.commit_event(event)
        # 记录事件提交信息
        logger.info(f"[HTTP Platform] HTTP request event committed: {method} {path}")

        # 返回响应
        return web.json_response({
            "status": "received",
            "message": "Request received and processed by bot",
            "request_id": abm.message_id
        })

    # ==================== 公共方法 ====================

    async def send_ws_message(self, message: Dict):
        """发送消息到所有连接的WebSocket客户端"""
        # 遍历所有WebSocket连接
        for ws in self._ws_connections:
            # 检查连接是否关闭
            if not ws.closed:
                try:
                    # 发送JSON消息
                    await ws.send_json(message)
                except Exception as e:
                    # 记录发送错误
                    logger.error(f"[HTTP Platform] Error sending WebSocket message: {e}")

    def get_connection_count(self) -> int:
        """获取当前WebSocket连接数"""
        return len(self._ws_connections)
