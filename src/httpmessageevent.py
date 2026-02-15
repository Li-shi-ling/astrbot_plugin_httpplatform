from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import MessageChain
from astrbot import logger

from .dataclasses import HTTPRequestData
from .constants import HTTP_MESSAGE_TYPE, HTTP_EVENT_TYPE
from .tool import BMC2Text

from collections.abc import AsyncGenerator
import asyncio
import json

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
    """标准 HTTP 消息事件
    特点：send方法直接处理完所有消息链条后发出去，send_streaming方法获取完所有数据后一并发出去
    """

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self._pending_response = None  # 保存待处理响应

    async def send(self, message_chain: MessageChain):
        """
        直接处理完整个消息链，立即返回响应
        """
        # 处理消息链
        full_response = []
        for message in message_chain.chain:
            response_text, text_type = BMC2Text(message)
            full_response.append({
                "content": response_text,
                "type": text_type
            })

        # 如果没有消息，返回空数组
        if not full_response:
            full_response = []

        # 获取待处理响应
        pending = None
        if self.event_id in self._adapter.pending_responses:
            pending = self._adapter.pending_responses.pop(self.event_id)
        elif self._pending_response:
            pending = self._pending_response

        # 设置响应结果
        if pending and not pending.future.done():
            result_json = json.dumps(full_response, ensure_ascii=False)
            pending.future.set_result(result_json)

            logger.debug(
                f"[StandardHTTPMessageEvent] 已发送响应 (event_id: {self.event_id}, 消息数: {len(full_response)})")
        else:
            logger.warning(f"[StandardHTTPMessageEvent] 没有找到待处理响应: event_id={self.event_id}")

    async def send_streaming(
            self,
            generator: AsyncGenerator[MessageChain, None],
            use_fallback: bool = False,
    ):
        """
        获取完所有流式数据后，一次性发送
        """
        # 收集所有流式数据
        collected_chains = []
        async for chain in generator:
            collected_chains.append(chain)

        # 如果没有收集到任何数据，直接返回
        if not collected_chains:
            return None

        # 合并所有消息链
        merged_chain = MessageChain()
        for chain in collected_chains:
            merged_chain.chain.extend(chain.chain)

        # 一次性发送合并后的消息
        await self.send(merged_chain)

        return None

class StreamHTTPMessageEvent(HTTPMessageEvent):
    """流式 HTTP 消息事件
    特点：send方法不处理（保持不动），send_streaming方法流式发送消息
    """

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, queue, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self.queue = queue
        self._is_streaming = False  # 标记是否正在流式传输
        self._stream_complete = asyncio.Event()  # 流式完成事件
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
        """
        流式发送消息到客户端

        这个方法会实时地将生成器产生的每个消息块发送给客户端，
        保持流式传输的特性
        """
        try:
            # 标记开始流式传输
            self._is_streaming = True
            self._stream_complete.clear()

            # 流式发送每个消息块
            async for message_chain in generator:
                for message in message_chain.chain:
                    response_text, text_type = BMC2Text(message)
                    await self.queue.put({
                        "type": HTTP_MESSAGE_TYPE["STREAM"],
                        "data": {"chunk": response_text},
                        "text_type": text_type
                    })

            # 发送流式结束标记
            await self.queue.put({
                "type": HTTP_MESSAGE_TYPE["END"],
                "data": {}
            })

            # 标记流式传输完成
            self._is_streaming = False
            self._stream_complete.set()

        except Exception as e:
            logger.error(f"[StreamHTTPMessageEvent] 流式发送时出错: {e}")

            # 发送错误信息
            try:
                await self.queue.put({
                    "type": HTTP_MESSAGE_TYPE["ERROR"],
                    "data": {"error": str(e)}
                })
                # 即使出错也要发送 END
                await self.queue.put({
                    "type": HTTP_MESSAGE_TYPE["END"],
                    "data": {"error": True}
                })
            except Exception as queue_error:
                logger.error(f"[StreamHTTPMessageEvent] 发送错误信息时失败: {queue_error}")

            # 标记流式传输完成（即使出错）
            self._is_streaming = False
            self._stream_complete.set()

            raise
