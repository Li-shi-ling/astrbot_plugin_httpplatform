import time
from typing import Optional
from .dataclasses import SessionStats
from astrbot.api import logger

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
        self._is_closed = False

    def update_activity(self):
        """更新会话活动时间"""
        if not self._is_closed:
            self.last_active = time.time()
            self.message_count += 1

    def is_closed(self) -> bool:
        """检查会话是否已关闭"""
        return self._is_closed

    def is_active(self) -> bool:
        """检查会话是否活跃"""
        return time.time() - self.last_active < self.adapter.session_timeout

    async def close(self, reason: str = "正常关闭"):
        """关闭会话"""
        logger.info(f"[HTTPAdapter] 会话关闭: {self.session_id}, 原因: {reason}")
        # 更新会话状态为已关闭
        self._is_closed = True
        self.last_active = time.time()
        # 可以添加其他清理逻辑，如释放资源等

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
