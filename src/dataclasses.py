"""
HTTP 适配器数据类定义
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class HTTPRequestData:
    """HTTP 请求数据"""
    method: str
    url: str
    headers: dict[str, str]
    remote_addr: str | None = None
    user_agent: str | None = None
    content_type: str | None = None
    accept: str | None = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class HTTPResponseData:
    """HTTP 响应数据"""
    status: int
    headers: dict[str, str]
    body: Any
    timestamp: float = field(default_factory=time.time)


@dataclass
class PendingResponse:
    """待处理响应"""
    future: asyncio.Future[Any]
    created_at: float = field(default_factory=time.time)
    timeout: int = 30
    session_id: str | None = None


@dataclass
class SessionStats:
    """会话统计信息"""
    session_id: str
    created_at: float
    last_active: float
    message_count: int = 0
    user_id: str | None = None
    username: str | None = None
    client_ip: str | None = None
    user_agent: str | None = None
    is_active: bool = True


@dataclass
class AdapterStats:
    """适配器统计信息"""
    timestamp: float
    sessions_active: int
    sessions_max_limit: int
    sessions_expired: int = 0
    pending_responses_active: int = 0
    pending_responses_expired: int = 0
    total_requests_processed: int = 0
    total_errors: int = 0
