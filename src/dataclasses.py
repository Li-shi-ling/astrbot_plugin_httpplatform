"""
HTTP 适配器数据类定义
"""
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
import asyncio

@dataclass
class HTTPRequestData:
    """HTTP 请求数据"""
    method: str
    url: str
    headers: Dict[str, str]
    remote_addr: Optional[str] = None
    user_agent: Optional[str] = None
    content_type: Optional[str] = None
    accept: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

@dataclass
class HTTPResponseData:
    """HTTP 响应数据"""
    status: int
    headers: Dict[str, str]
    body: Any
    timestamp: float = field(default_factory=time.time)


@dataclass
class PendingResponse:
    """待处理响应"""
    future: asyncio.Future
    created_at: float = field(default_factory=time.time)
    timeout: int = 30
    session_id: Optional[str] = None


@dataclass
class SessionStats:
    """会话统计信息"""
    session_id: str
    created_at: float
    last_active: float
    message_count: int = 0
    user_id: Optional[str] = None
    username: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
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