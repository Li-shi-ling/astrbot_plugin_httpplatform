import asyncio
import json
import random
import time
import uuid
from collections.abc import Coroutine
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp import web

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

from .event import HttpMessageEvent


@register_platform_adapter(
    "httpplatform",
    "HTTP 适配器平台 - 支持 WebSocket 到 HTTP 的转换",
    default_config_tmpl={
        "http_port": 8080,
        "ws_port": 8081,
        "api_base": "http://localhost:8080",
        "ws_url": "ws://localhost:8081",
        "token": "",
    },
)
class HttpPlatformAdapter(Platform):
    """HTTP platform adapter implementation with WebSocket to HTTP conversion."""

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)

        self.settings = platform_settings
        self.http_port = platform_config.get("http_port", 8080)
        self.ws_port = platform_config.get("ws_port", 8081)
        self.api_base = platform_config.get("api_base", f"http://localhost:{self.http_port}")
        self.ws_url = platform_config.get("ws_url", f"ws://localhost:{self.ws_port}")
        self.token = platform_config.get("token", "")

        # id 从 platform_config 获取，是该适配器实例的唯一标识
        platform_id = platform_config.get("id", "httpplatform_default")
        self._metadata = PlatformMetadata(
            name="httpplatform",
            description="HTTP 适配器平台",
            id=platform_id,
        )

        # WebSocket server state
        self._ws_server: web.TCPSite | None = None
        self._ws_app: web.Application | None = None
        self._ws_connections: List[web.WebSocketResponse] = []

        # HTTP server state
        self._http_server: web.TCPSite | None = None
        self._http_app: web.Application | None = None

        # Bot user info
        self.bot_user_id: str = str(uuid.uuid4())

        # Running tasks
        self._tasks: list[asyncio.Task] = []

    def meta(self) -> PlatformMetadata:
        return self._metadata

    async def send_by_session(
        self,
        session: MessageSesion,
        message_chain: MessageChain,
    ):
        """Send message through session."""
        await super().send_by_session(session, message_chain)

    def run(self) -> Coroutine[Any, Any, None]:
        """Main entry point for the adapter."""
        return self._run()

    async def _run(self):
        """Run the adapter with WebSocket and HTTP servers."""
        logger.info("[HTTP Platform] Starting HTTP platform adapter...")

        # Start WebSocket server
        ws_task = asyncio.create_task(self._start_ws_server())
        self._tasks.append(ws_task)

        # Start HTTP server
        http_task = asyncio.create_task(self._start_http_server())
        self._tasks.append(http_task)

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info("[HTTP Platform] Adapter tasks cancelled")

    async def terminate(self):
        """Terminate the adapter."""
        logger.info("[HTTP Platform] Terminating adapter...")

        for task in self._tasks:
            if not task.done():
                task.cancel()

        # Close WebSocket server
        if self._ws_server:
            await self._ws_server.stop()

        # Close HTTP server
        if self._http_server:
            await self._http_server.stop()

        # Close all WebSocket connections
        for ws in self._ws_connections:
            if not ws.closed:
                await ws.close()

    # ==================== WebSocket Server ====================

    async def _start_ws_server(self):
        """Start WebSocket server."""
        app = web.Application()
        app.add_routes([
            web.get('/ws', self._handle_ws_connection)
        ])

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.ws_port)
        self._ws_server = site
        self._ws_app = app

        logger.info(f"[HTTP Platform] WebSocket server starting on port {self.ws_port}")
        await site.start()
        logger.info(f"[HTTP Platform] WebSocket server started on ws://localhost:{self.ws_port}/ws")

        # Keep the server running
        while True:
            await asyncio.sleep(3600)

    async def _handle_ws_connection(self, request):
        """Handle WebSocket connection."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self._ws_connections.append(ws)
        logger.info(f"[HTTP Platform] New WebSocket connection established")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(ws, msg.data)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"[HTTP Platform] WebSocket error: {ws.exception()}")
        finally:
            if ws in self._ws_connections:
                self._ws_connections.remove(ws)
            logger.info(f"[HTTP Platform] WebSocket connection closed")

    async def _handle_ws_message(self, ws: web.WebSocketResponse, message_data: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message_data)
            msg_type = data.get("type")
            logger.debug(f"[HTTP Platform] Received WS message: {msg_type}")

            if msg_type == "http_request":
                await self._handle_http_request_via_ws(ws, data)
            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})
        except json.JSONDecodeError as e:
            logger.error(f"[HTTP Platform] Invalid JSON in WebSocket message: {e}")
            await ws.send_json({"type": "error", "error": "Invalid JSON"})
        except Exception as e:
            logger.error(f"[HTTP Platform] Error handling WebSocket message: {e}")
            await ws.send_json({"type": "error", "error": str(e)})

    async def _handle_http_request_via_ws(self, ws: web.WebSocketResponse, data: Dict):
        """Handle HTTP request received via WebSocket."""
        request_id = data.get("request_id", str(uuid.uuid4()))
        method = data.get("method", "GET")
        path = data.get("path", "/")
        headers = data.get("headers", {})
        body = data.get("body", {})

        logger.info(f"[HTTP Platform] Received HTTP request via WS: {method} {path}")

        # Convert WebSocket message to HTTP request
        try:
            # Create HTTP request
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_base}{path}"
                logger.debug(f"[HTTP Platform] Sending HTTP request to: {url}")

                # Handle different HTTP methods
                if method == "GET":
                    async with session.get(url, headers=headers, params=body) as response:
                        response_data = await response.json()
                        status = response.status
                elif method == "POST":
                    async with session.post(url, headers=headers, json=body) as response:
                        response_data = await response.json()
                        status = response.status
                elif method == "PUT":
                    async with session.put(url, headers=headers, json=body) as response:
                        response_data = await response.json()
                        status = response.status
                elif method == "DELETE":
                    async with session.delete(url, headers=headers) as response:
                        response_data = await response.json()
                        status = response.status
                else:
                    response_data = {"error": "Method not allowed"}
                    status = 405

                # Send HTTP response back via WebSocket
                await ws.send_json({
                    "type": "http_response",
                    "request_id": request_id,
                    "status": status,
                    "headers": dict(response.headers),
                    "body": response_data
                })
                logger.info(f"[HTTP Platform] Sent HTTP response via WS: {status} {path}")

        except Exception as e:
            logger.error(f"[HTTP Platform] Error processing HTTP request: {e}")
            await ws.send_json({
                "type": "http_response",
                "request_id": request_id,
                "status": 500,
                "headers": {},
                "body": {"error": str(e)}
            })

    # ==================== HTTP Server ====================

    async def _start_http_server(self):
        """Start HTTP server."""
        app = web.Application()
        app.add_routes([
            web.get('/{tail:.*}', self._handle_http_get),
            web.post('/{tail:.*}', self._handle_http_post),
            web.put('/{tail:.*}', self._handle_http_put),
            web.delete('/{tail:.*}', self._handle_http_delete),
        ])

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.http_port)
        self._http_server = site
        self._http_app = app

        logger.info(f"[HTTP Platform] HTTP server starting on port {self.http_port}")
        await site.start()
        logger.info(f"[HTTP Platform] HTTP server started on http://localhost:{self.http_port}")

        # Keep the server running
        while True:
            await asyncio.sleep(3600)

    async def _handle_http_get(self, request):
        """Handle HTTP GET request."""
        return await self._handle_http_request(request, "GET")

    async def _handle_http_post(self, request):
        """Handle HTTP POST request."""
        return await self._handle_http_request(request, "POST")

    async def _handle_http_put(self, request):
        """Handle HTTP PUT request."""
        return await self._handle_http_request(request, "PUT")

    async def _handle_http_delete(self, request):
        """Handle HTTP DELETE request."""
        return await self._handle_http_request(request, "DELETE")

    async def _handle_http_request(self, request, method):
        """Handle HTTP request."""
        path = request.path
        headers = dict(request.headers)

        try:
            body = await request.json()
        except json.JSONDecodeError:
            body = {}

        logger.info(f"[HTTP Platform] Received HTTP request: {method} {path}")

        # Create message event for the bot
        formatted_message = (
            f"[HTTP Request] {method} {path}\n"  
            f"Headers: {json.dumps(headers, indent=2)}\n"  
            f"Body: {json.dumps(body, indent=2)}"
        )

        abm = AstrBotMessage()
        abm.self_id = self.bot_user_id
        abm.sender = MessageMember(
            user_id="http_client",
            nickname="HTTP Client",
        )
        abm.type = MessageType.GROUP_MESSAGE
        abm.session_id = "http_platform_session"
        abm.message_id = str(uuid.uuid4())
        abm.message = [Plain(text=formatted_message)]
        abm.message_str = formatted_message
        abm.raw_message = {
            "method": method,
            "path": path,
            "headers": headers,
            "body": body
        }
        abm.timestamp = int(time.time())

        event = HttpMessageEvent(
            message_str=formatted_message,
            message_obj=abm,
            platform_meta=self._metadata,
            session_id="http_platform_session",
            adapter=self,
        )

        event.set_extra("method", method)
        event.set_extra("path", path)
        event.set_extra("headers", headers)
        event.set_extra("body", body)

        event.is_wake = True
        event.is_at_or_wake_command = True

        self.commit_event(event)
        logger.info(f"[HTTP Platform] HTTP request event committed: {method} {path}")

        # Return a response
        return web.json_response({
            "status": "received",
            "message": "Request received and processed by bot",
            "request_id": abm.message_id
        })

    # ==================== Public Methods ====================

    async def send_ws_message(self, message: Dict):
        """Send message to all connected WebSocket clients."""
        for ws in self._ws_connections:
            if not ws.closed:
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logger.error(f"[HTTP Platform] Error sending WebSocket message: {e}")

    def get_connection_count(self) -> int:
        """Get current WebSocket connection count."""
        return len(self._ws_connections)
