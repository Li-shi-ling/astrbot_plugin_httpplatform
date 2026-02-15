import time
from typing import Any, Dict, List, Optional
from .constants import HTTP_MESSAGE_TYPE, HTTP_EVENT_TYPE, HTTP_STATUS_CODE, WS_CLOSE_CODE
from .dataclasses import HTTPRequestData, PendingResponse, SessionStats, AdapterStats
from astrbot.api.message_components import Plain
import asyncio
import uuid
from astrbot import logger
from .httpmessageevent import WebSocketMessageEvent
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
    register_platform_adapter,
)
import json

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
            user_agent=self.user_agent,
            data=data
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
