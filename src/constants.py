"""
HTTP 适配器常量定义
"""
from types import MappingProxyType
# ==================== HTTP 消息类型常量 ====================
HTTP_MESSAGE_TYPE = MappingProxyType({
    "MESSAGE": "message",
    "PING": "ping",
    "PONG": "pong",
    "ACK": "ack",
    "RESPONSE": "response",
    "ERROR": "error",
    "CONNECTED": "connected",
    "COMPLETE": "complete",
    "STREAM": "stream",
    "TIMEOUT": "timeout",
    "END": "end"
})

# ==================== HTTP 事件类型常量 ====================
HTTP_EVENT_TYPE = MappingProxyType({
    "HTTP_REQUEST": "http_request",
    "STREAMING": "streaming"
})

# ==================== HTTP 状态码常量 ====================
HTTP_STATUS_CODE = MappingProxyType({
    "OK": 200,
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "TIMEOUT": 504,
    "INTERNAL_ERROR": 500
})

