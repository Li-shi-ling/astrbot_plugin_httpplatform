"""
HTTP 适配器常量定义
"""

# ==================== HTTP 消息类型常量 ====================
HTTP_MESSAGE_TYPE = {
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
}

# ==================== HTTP 事件类型常量 ====================
HTTP_EVENT_TYPE = {
    "HTTP_REQUEST": "http_request",
    "WEBSOCKET": "websocket",
    "STREAMING": "streaming"
}

# ==================== HTTP 状态码常量 ====================
HTTP_STATUS_CODE = {
    "OK": 200,
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
    "TIMEOUT": 504,
    "INTERNAL_ERROR": 500
}

# ==================== WebSocket 关闭代码 ====================
WS_CLOSE_CODE = {
    "NORMAL_CLOSURE": 1000,
    "GOING_AWAY": 1001,
    "PROTOCOL_ERROR": 1002,
    "UNSUPPORTED_DATA": 1003,
    "NO_STATUS_RECEIVED": 1005,
    "ABNORMAL_CLOSURE": 1006,
    "INVALID_FRAME_PAYLOAD_DATA": 1007,
    "POLICY_VIOLATION": 1008,
    "MESSAGE_TOO_BIG": 1009,
    "MANDATORY_EXTENSION": 1010,
    "INTERNAL_ERROR": 1011,
    "SERVICE_RESTART": 1012,
    "TRY_AGAIN_LATER": 1013,
    "BAD_GATEWAY": 1014
}