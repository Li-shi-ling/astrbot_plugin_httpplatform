from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from .src import HttpPlatformAdapter, HttpMessageEvent

@register("httpplatform", "AstrBot Team", "HTTP 适配器平台 - 支持 WebSocket 到 HTTP 的转换", "1.0.0")
class HttpPlatformPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        logger.info("[HTTP Platform] Initializing HTTP Platform Plugin")

    async def initialize(self):
        """初始化 HTTP 平台插件"""
        logger.info("[HTTP Platform] HTTP Platform Plugin initialized")

    @filter.command("httpstatus")
    async def httpstatus(self, event: AstrMessageEvent):
        """查看 HTTP 平台状态"""
        # 这里可以添加获取平台状态的逻辑
        yield event.plain_result("HTTP Platform is running")

    async def terminate(self):
        """销毁 HTTP 平台插件"""
        logger.info("[HTTP Platform] HTTP Platform Plugin terminated")

# 确保适配器被注册
try:
    # 导入适配器以确保它被注册
    from .src.Platform import HttpPlatformAdapter
    logger.info("[HTTP Platform] HTTP Platform Adapter imported and registered")
except Exception as e:
    logger.error(f"[HTTP Platform] Error importing adapter: {e}")
