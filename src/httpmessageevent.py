from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import MessageChain
from astrbot.api import logger

from .dataclasses import HTTPRequestData
from .constants import HTTP_MESSAGE_TYPE, HTTP_EVENT_TYPE
from .tool import BMC2Dict

from collections.abc import AsyncGenerator
import asyncio

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
            logger.error(f"[HTTPMessageEvent] 流式发送时出错: {e}", exc_info=True)
            raise

class StandardHTTPMessageEvent(HTTPMessageEvent):
    """标准 HTTP 消息事件
    特点：send方法只缓存数据，不立即返回响应；由 on_llm_response 统一输出
    """

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self._cached_response = []  # 缓存完整的响应数据
        self._finalcall = False

    async def send(self, message_chain: MessageChain):
        """
        缓存消息链数据，不立即发送响应
        """
        # 处理消息链
        full_response = []
        for message in message_chain.chain:
            response_json, text_type = BMC2Dict(message)
            full_response.append({
                "content": response_json,
                "type": text_type
            })

        # 如果没有消息，返回空数组
        if not full_response:
            full_response = []

        # 缓存完整的响应数据
        self._cached_response.extend(full_response)
        logger.debug(f"[StandardHTTPMessageEvent] 已缓存响应数据 (event_id: {self.event_id}, 消息数: {len(full_response)})")

        if self._finalcall:
            await self.send_response()
            self._finalcall = False

    async def send_streaming(
            self,
            generator: AsyncGenerator[MessageChain, None],
            use_fallback: bool = False,
    ):
        """
        获取完所有流式数据后，一次性缓存
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

        # 一次性缓存合并后的消息
        await self.send(merged_chain)

        return None

    async def send_response(self):
        """
        发送缓存的响应 - 专门用于在 on_llm_response 中调用
        """
        # 如果没有缓存数据，发送空响应
        if self._cached_response is None:
            self._cached_response = []

        # 获取待处理响应
        pending = None
        if self.event_id in self._adapter.pending_responses:
            pending = self._adapter.pending_responses.pop(self.event_id)

        # 设置响应结果
        if pending and not pending.future.done():
            result_json = self._cached_response
            pending.future.set_result(result_json)

            logger.debug(f"[StandardHTTPMessageEvent] 已发送响应 (event_id: {self.event_id}, 消息数: {len(self._cached_response)})")
        else:
            logger.warning(f"[StandardHTTPMessageEvent] 没有找到待处理响应: event_id={self.event_id}")

    def set_final_call(self):
        self._finalcall = True

    def get_has_send_oper(self):
        return getattr(self, "_has_send_oper", False)

class StreamHTTPMessageEvent(HTTPMessageEvent):
    """流式 HTTP 消息事件
    特点：send方法不处理（保持不动），send_streaming方法流式发送消息（不发送结束信号）
    """

    def __init__(self, message_str, message_obj, platform_meta, session_id, adapter, queue, event_id, request_data):
        super().__init__(message_str, message_obj, platform_meta, session_id, adapter, event_id, request_data)
        self.queue = queue
        self._is_streaming = False
        self._stream_complete = asyncio.Event()
        self.set_extra("streaming", True)
        self._finalcall = False

    async def send(self, message_chain: MessageChain):
        """发送完整响应 - 用于非流式输出"""
        # 如果正在流式传输，需要先结束流式
        if self._is_streaming:
            await self._end_streaming()

        # 发送完整消息（这将发送多条消息，但不会发送结束信号）
        for message in message_chain.chain:
            response_text, text_type = BMC2Dict(message)
            success = await self._safe_put({
                "type": HTTP_MESSAGE_TYPE["MESSAGE"],
                "data": {"content": response_text},
                "text_type": text_type
            })
            if not success:
                self._is_streaming = False
                break

        if self._finalcall:
            await self.send_end_signal()
            self._finalcall = False

    async def send_streaming(
            self,
            generator: AsyncGenerator[MessageChain, None],
            use_fallback: bool = False,
    ):
        """
        流式发送消息到客户端

        这个方法会实时地将生成器产生的每个消息块发送给客户端，
        保持流式传输的特性。
        """
        try:
            # 标记开始流式传输
            self._is_streaming = True
            self._stream_complete.clear()

            # 流式发送每个消息块
            await self.queue_put_generator(generator)
            self._finalcall = True

            # 注意：这里不再发送 END 信号，只标记内部完成
            self._is_streaming = False
            self._stream_complete.set()

        except Exception as e:
            logger.error(f"[StreamHTTPMessageEvent] 流式发送时出错: {e}", exc_info=True)

            # 发送错误信息（错误时仍然需要通知客户端）
            try:
                success = await self._safe_put({
                    "type": HTTP_MESSAGE_TYPE["ERROR"],
                    "data": {"error": str(e)}
                })
                if not success:
                    self._is_streaming = False
            except Exception as queue_error:
                logger.error(f"[StreamHTTPMessageEvent] 发送错误信息时失败: {queue_error}", exc_info=True)

            # 标记流式传输完成（即使出错）
            self._is_streaming = False
            self._stream_complete.set()

            raise

        if self._finalcall:
            await self.send_end_signal()
            self._finalcall = False

    async def _end_streaming(self):
        """结束当前的流式传输（内部使用，不对外发送结束信号）"""
        if self._is_streaming:
            self._is_streaming = False
            self._stream_complete.set()

    async def send_end_signal(self):
        """
        发送流式结束信号 - 专门用于在 on_llm_response 中调用
        """
        # 确保流式传输已经完成
        if self._is_streaming:
            # 等待流式传输完成（但最多等待5秒）
            try:
                await asyncio.wait_for(self._stream_complete.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"[StreamHTTPMessageEvent] 等待流式完成超时 (event_id: {self.event_id})")
                self._is_streaming = False

        # 发送结束信号
        success = await self._safe_put({
            "type": HTTP_MESSAGE_TYPE["END"],
            "data": {}
        })
        if not success:
            self._is_streaming = False
        logger.debug(f"[StreamHTTPMessageEvent] 已发送结束信号 (event_id: {self.event_id})")

    def set_final_call(self):
        self._finalcall = True

    async def queue_put_generator(self, generator):
        async for message_chain in generator:
            if not self._is_streaming:
                break
            for message in message_chain.chain:
                response_text, text_type = BMC2Dict(message)

                success = await self._safe_put({
                    "type": HTTP_MESSAGE_TYPE["MESSAGE"],
                    "data": {"content": response_text},
                    "text_type": text_type
                })
                if not success:
                    # 队列持续满，停止生成
                    self._is_streaming = False
                    break

    def get_has_send_oper(self):
        return getattr(self, "_has_send_oper", False)

    async def _safe_put(self, item: dict, timeout: float = 1.0):
        """安全入队，防止反压阻塞"""
        try:
            await asyncio.wait_for(self.queue.put(item), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(
                f"[StreamHTTPMessageEvent] 队列已满，丢弃消息 (event_id: {self.event_id})"
            )
            return False
