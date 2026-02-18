import time
from typing import Any, Dict, List, Optional
from .constants import HTTP_MESSAGE_TYPE, HTTP_EVENT_TYPE, HTTP_STATUS_CODE
from .dataclasses import HTTPRequestData, PendingResponse, SessionStats, AdapterStats
from astrbot.api.message_components import Plain
import asyncio
import uuid
from astrbot.api import logger
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

    def __init__(self, session_id: str, adapter, client_ip: Optional[str] = None, user_agent: Optional[str] = None):
        self.session_id = session_id
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

    async def close(self, reason: str = "正常关闭"):
        """关闭会话"""
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
