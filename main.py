# 导入事件过滤器和事件类
from astrbot.api.event import filter, AstrMessageEvent, MessageEventResult
# 导入上下文、插件基类和注册装饰器
from astrbot.api.star import Context, Star, register
# 导入日志模块
from astrbot.api import logger
# 导入HTTP平台适配器和消息事件类
from .src import HttpPlatformAdapter, HttpMessageEvent

# 注册HTTP平台插件
@register("httpplatform", "AstrBot Team", "HTTP 适配器平台 - 支持 WebSocket 到 HTTP 的转换", "1.0.0")
class HttpPlatformPlugin(Star):
    """HTTP平台插件类"""
    
    def __init__(self, context: Context):
        super().__init__(context)
        try:
            from .src.Platform import HttpPlatformAdapter
            logger.info("[HTTP Platform] HTTP Platform Adapter imported and registered")
        except Exception as e:
            logger.error(f"[HTTP Platform] Error importing adapter: {e}")

    async def initialize(self):
        """初始化 HTTP 平台插件"""
        # 记录初始化完成信息
        logger.info("[HTTP Platform] HTTP Platform Plugin initialized")

    @filter.command("httpstatus")
    async def httpstatus(self, event: AstrMessageEvent):
        """查看 HTTP 平台状态
        
        命令: /httpstatus
        描述: 查看 HTTP 平台的运行状态
        """
        # 这里可以添加获取平台状态的逻辑
        # 返回平台状态信息
        yield event.plain_result("HTTP Platform is running")

    async def terminate(self):
        """销毁 HTTP 平台插件"""
        # 记录销毁信息
        logger.info("[HTTP Platform] HTTP Platform Plugin terminated")

