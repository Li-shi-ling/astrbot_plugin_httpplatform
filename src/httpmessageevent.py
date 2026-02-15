from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import MessageChain
from .dataclasses import HTTPRequestData, PendingResponse, SessionStats, AdapterStats
from .constants import HTTP_MESSAGE_TYPE, HTTP_EVENT_TYPE, HTTP_STATUS_CODE
from collections.abc import AsyncGenerator
from astrbot import logger
from .tool import BMC2Text
import asyncio
import json
import time

# ==================== HTTP 消息事件类 ====================
class HTTPMessageEvent(AstrMessageEvent):
    """HTTP 消息事件基类"""

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data):
        # 调用父类初始化
        super().__init__(message_str, message_obj, platform_meta, session_id)

        # 设置自定义属性
        self._adapter = adapter
        self.event_id = event_id
        self.http_request_data = request_data
        self._raw_headers = request_data.headers

        # 设置额外信息
        self._set_extra_info(request_data)

        # 初始化状态属性
        self.is_wake = True
        self.is_at_or_wake_command = True

    def _set_extra_info(self, request_data: HTTPRequestData):
        """设置额外信息"""
        self.set_extra("event_id", self.event_id)
        self.set_extra("event_type", HTTP_EVENT_TYPE["HTTP_REQUEST"])
        self.set_extra("http_request", True)
        self.set_extra("request_method", request_data.method)
        self.set_extra("request_url", request_data.url)
        self.set_extra("request_headers", dict(request_data.headers))
        self.set_extra("remote_addr", request_data.remote_addr)
        self.set_extra("user_agent", request_data.user_agent)
        self.set_extra("content_type", request_data.content_type)
        self.set_extra("accept", request_data.accept)
        self.set_extra("request_timestamp", request_data.timestamp)

    @property
    def adapter(self):
        """获取适配器实例"""
        return self._adapter

    @property
    def headers(self):
        """获取原始请求头"""
        return self._raw_headers

    async def send(self, message_chain: MessageChain):
        """发送响应"""
        raise NotImplementedError("子类必须实现 send 方法")

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ):
        """发送流式消息到消息平台，使用异步生成器"""
        # HTTP 适配器的流式处理
        try:
            async for message_chain in generator:
                # 对于 HTTP 适配器，流式发送实际上就是调用 send 方法
                await self.send(message_chain)
        except Exception as e:
            logger.error(f"[HTTPMessageEvent] 流式发送时出错: {e}")
            raise

class StandardHTTPMessageEvent(HTTPMessageEvent):
    """标准 HTTP 消息事件"""

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self._message_buffer = []  # 消息缓冲区，收集所有消息

    async def send(self, message_chain: MessageChain):
        """重写 send 方法，收集消息而不是立即返回"""
        response_text = str(message_chain)
        self._message_buffer.append(response_text)

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ):
        """发送流式消息到消息平台，使用异步生成器"""
        # 对于标准 HTTP 适配器，流式发送自动转变为普通发送
        try:
            async for message_chain in generator:
                await self.send(message_chain)
        except Exception as e:
            logger.error(f"[StandardHTTPMessageEvent] 流式发送时出错: {e}")
            raise

    async def mark_conversation_end(self):
        """标记对话结束，返回所有收集的消息"""
        if self.event_id in self._adapter.pending_responses:
            pending = self._adapter.pending_responses.pop(self.event_id)
            if not pending.future.done():
                # 将所有收集的消息合并为一个响应
                full_response = "\n".join(self._message_buffer)
                pending.future.set_result(full_response)

    def set_result(self, result):
        """重写set_result方法，在设置结果时调用mark_conversation_end"""
        super().set_result(result)
        # 启动一个任务来调用mark_conversation_end
        import asyncio
        asyncio.create_task(self.mark_conversation_end())

class StreamHTTPMessageEvent(HTTPMessageEvent):
    """流式 HTTP 消息事件"""

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, queue, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self.queue = queue
        self._message_buffer = []  # 新增：消息缓冲区
        self._is_streaming = False  # 新增：是否正在流式传输
        self._stream_complete = asyncio.Event()  # 新增：流式完成事件
        self.set_extra("event_type", HTTP_EVENT_TYPE["STREAMING"])
        self.set_extra("streaming", True)

    async def send(self, message_chain: MessageChain):
        """发送完整响应 - 这是单条消息的结束"""
        # 如果正在流式传输，先发送流式结束
        if self._is_streaming:
            await self._end_streaming()

        for message in message_chain.chain:
            response_text, text_type = BMC2Text(message)
            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["STREAM"],
                "data": {"chunk": response_text},
                "text_type": text_type
            })
        # 注意：不发送 END，因为可能还有后续消息

    async def _end_streaming(self):
        """结束当前的流式传输"""
        if self._is_streaming:
            self._is_streaming = False
            self._stream_complete.set()

    async def send_streaming(
            self,
            generator: AsyncGenerator[MessageChain, None],
            use_fallback: bool = False,
    ):
        """发送流式消息到消息平台，使用异步生成器"""
        try:
            async for message_chain in generator:
                for message in message_chain.chain:
                    response_text, text_type = BMC2Text(message)
                    await self.queue.put({
                        "type": HTTP_MESSAGE_TYPE["STREAM"],
                        "data": {"chunk": response_text},
                        "text_type": text_type
                    })

            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["END"],
                "data": {}
            })

        except Exception as e:
            logger.error(f"[StreamHTTPMessageEvent] 流式发送时出错: {e}")
            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["ERROR"],
                "data": {"error": str(e)}
            })
            # 即使出错也要发送 END
            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["END"],
                "data": {"error": True}
            })

    async def mark_conversation_end(self):  # 1. 改为 async 方法
        """标记整个对话结束"""
        # 2. 直接 await，确保任务在 Event 对象销毁前执行完成
        await self._end_streaming()

        # 3. 确保 END 信号入队
        await self.queue.put({
            "type": HTTP_MESSAGE_TYPE["END"],
            "data": {}
        })
