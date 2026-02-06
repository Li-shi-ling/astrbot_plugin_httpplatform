# 从__future__导入annotations，支持类型注解的前向引用
from __future__ import annotations

# 导入类型检查模块
from typing import TYPE_CHECKING

# 导入日志模块
from astrbot import logger
# 导入消息事件基类和消息链类
from astrbot.api.event import AstrMessageEvent, MessageChain

# 类型检查时导入HttpPlatformAdapter
if TYPE_CHECKING:
    from .Platform import HttpPlatformAdapter

class HttpMessageEvent(AstrMessageEvent):
    """HTTP平台的消息事件类

    此类处理HTTP平台的交互。
    """

    def __init__(
            self,
            message_str: str,  # 消息字符串
            message_obj,  # 消息对象
            platform_meta,  # 平台元数据
            session_id: str,  # 会话ID
            adapter: HttpPlatformAdapter,  # HTTP平台适配器实例
    ):
        # 调用父类构造函数
        super().__init__(message_str, message_obj, platform_meta, session_id)
        # 保存适配器实例
        self._adapter = adapter

    @property
    def adapter(self) -> HttpPlatformAdapter:
        """获取适配器实例"""
        return self._adapter

    async def send(self, message: MessageChain | None):
        """HTTP平台的发送方法

        对于HTTP平台，我们可以将消息发送回连接的WebSocket客户端。
        """
        if message:
            # 将消息链转换为文本
            message_text = "".join([str(comp) for comp in message])
            # 记录发送消息的信息
            logger.debug(f"[HTTP Platform] send() called with message: {message_text}")
            
            # 发送消息到所有连接的WebSocket客户端
            await self._adapter.send_ws_message({
                "type": "bot_message",  # 消息类型
                "content": message_text,  # 消息内容
                "timestamp": int(self.message_obj.timestamp)  # 时间戳
            })

    async def send_streaming(self, message_chain: MessageChain, use_fallback: bool = False):
        """HTTP平台的流式发送方法

        对于HTTP平台，我们可以将流式消息发送回连接的WebSocket客户端。
        
        参数:
            message_chain: 消息链
            use_fallback: 是否使用 fallback 模式
        """
        # 将消息链转换为文本
        message_text = "".join([str(comp) for comp in message_chain])
        # 记录发送流式消息的信息
        logger.debug(f"[HTTP Platform] send_streaming() called with message: {message_text}")
        
        # 发送流式消息到所有连接的WebSocket客户端
        await self._adapter.send_ws_message({
            "type": "bot_message_streaming",  # 消息类型
            "content": message_text,  # 消息内容
            "timestamp": int(self.message_obj.timestamp)  # 时间戳
        })

    def get_http_context(self) -> dict:
        """获取当前HTTP请求的上下文信息

        对需要了解HTTP请求上下文的插件很有用。
        """
        return {
            "method": self.get_extra("method"),  # HTTP方法
            "path": self.get_extra("path"),  # 请求路径
            "headers": self.get_extra("headers", {}),  # 请求头
            "body": self.get_extra("body", {}),  # 请求体
            "request_id": self.message_obj.message_id  # 请求ID
        }
