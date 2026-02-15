"""
AstrBot HTTP Adapter 示例程序

这个示例展示如何使用 HTTP 适配器为 AstrBot 提供外部 HTTP 接口。
通过 HTTP 适配器，外部应用可以通过 HTTP/HTTPS 协议访问 AstrBot。

主要功能：
1. 启动 HTTP 服务器，提供 REST API 接口
2. 提供会话管理和统计信息
3. 完整的鉴权和安全控制
"""

from astrbot.api.star import Context, Star, register
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.api import logger


# ==================== HTTP 适配器插件 ====================
class HTTPAdapterPlugin(Star):
    """
    HTTP 适配器插件

    这个插件注册 HTTP 适配器，并提供配置管理功能。
    通过此适配器，外部应用可以通过 HTTP/HTTPS 访问 AstrBot。
    """

    # 插件配置项定义
    _http_adapter_config_items = {
        "http_host": {
            "description": "HTTP 服务器监听地址",
            "type": "string",
            "hint": "HTTP 服务器绑定的主机地址，默认 0.0.0.0",
            "default": "0.0.0.0"
        },
        "http_port": {
            "description": "HTTP 服务器监听端口",
            "type": "int",
            "hint": "HTTP 服务器监听的端口号，默认 8080",
            "default": 8080,
            "min": 1,
            "max": 65535
        },
        "api_prefix": {
            "description": "API 路径前缀",
            "type": "string",
            "hint": "API 接口的路径前缀，默认 /api/v1",
            "default": "/api/v1"
        },
        
        "enable_http_api": {
            "description": "启用 HTTP API",
            "type": "bool",
            "hint": "是否启用 HTTP API 支持",
            "default": True
        },
        "auth_token": {
            "description": "鉴权令牌",
            "type": "password",
            "hint": "用于 API 访问的 Bearer Token，留空表示不启用鉴权",
            "default": ""
        },
        "cors_origins": {
            "description": "CORS 允许的源",
            "type": "string",
            "hint": "CORS 允许的源，多个用逗号分隔，* 表示允许所有",
            "default": "*"
        },
        "max_request_size": {
            "description": "最大请求大小",
            "type": "int",
            "hint": "最大请求体大小（字节），默认 10MB",
            "default": 10485760
        },
        "request_timeout": {
            "description": "请求超时时间",
            "type": "int",
            "hint": "HTTP 请求超时时间（秒），默认 30",
            "default": 30
        },
        "session_timeout": {
            "description": "会话超时时间",
            "type": "int",
            "hint": "会话超时时间（秒），默认 3600（1小时）",
            "default": 3600
        },
        "max_sessions": {
            "description": "最大会话数",
            "type": "int",
            "hint": "最大同时连接的会话数，默认 1000",
            "default": 1000
        }
    }

    _registered: bool = False

    def __init__(self, context: Context):
        super().__init__(context)

        # 导入 HTTP 适配器以注册它
        # 装饰器会自动注册适配器
        try:
            import astrbot.cli
            version = None
            if hasattr(astrbot.cli, '__version__'):
                version = astrbot.cli.__version__
            if not version:
                logger.warning("[astrbook] 没有找到astrbot版本号,使用4.14.8前的metadata注册方案")
                self._register_config()
                from .src.http_adapter_414 import HTTPAdapter
            else:
                v1 = [int(x) for x in version.split('.')]
                v2 = [int(x) for x in "4.16.0".split('.')]
                max_len = max(len(v1), len(v2))
                v1 += [0] * (max_len - len(v1))
                v2 += [0] * (max_len - len(v2))
                if v1 >= v2:
                    from .src.http_adapter_416 import HTTPAdapter
                else:
                    from .src.http_adapter_414 import HTTPAdapter
            self._http_adapter_cls = HTTPAdapter
            logger.info("[HTTPAdapter] HTTP 适配器导入成功")
        except ImportError as e:
            logger.error(f"[HTTPAdapter] 导入 HTTP 适配器失败: {e}")
            raise

    def _register_config(self):
        """注册配置信息到平台"""
        if self._registered:
            return False

        try:
            target_dict = CONFIG_METADATA_2["platform_group"]["metadata"]["platform"]["items"]
            for name in list(self._http_adapter_config_items):
                if name not in target_dict:
                    target_dict[name] = self._http_adapter_config_items[name]
        except Exception as e:
            logger.error(f"[HTTPAdapter] 注册平台元数据时出错: {e}", exc_info=True)
            return False

        self._registered = True
        logger.info("[HTTPAdapter] 配置信息注册成功")
        return True

    def _unregister_config(self):
        """从平台中移除配置信息"""
        if not self._registered:
            return False

        try:
            target_dict = CONFIG_METADATA_2["platform_group"]["metadata"]["platform"]["items"]
            for name in list(self._http_adapter_config_items):
                if name in target_dict:
                    target_dict.pop(name, None)
        except Exception as e:
            logger.error(f"[HTTPAdapter] 清理平台元数据时出错: {e}", exc_info=True)
            return False

        self._registered = False
        logger.info("[HTTPAdapter] 配置信息清理成功")
        return True

    async def initialize(self):
        """初始化插件"""
        self._register_config()
        logger.info("[HTTPAdapter] HTTP 适配器插件初始化完成")

    async def terminate(self):
        """终止插件"""
        self._unregister_config()
        logger.info("[HTTPAdapter] HTTP 适配器插件终止")

    @filter.command_group("http")
    async def http(self):
        pass

    @http.command("ghp")
    async def inithttpadapter(self, event: AstrMessageEvent):
        """获取所有HTTPAdapter实例到内存"""
        self.httpadapter = {}
        for platform in self.context.platform_manager.platform_insts:
            if isinstance(platform, self._http_adapter_cls):
                meta = platform.meta()
                if hasattr(meta, 'id'):
                    platform_id = meta.id
                else:
                    platform_id = None
                if platform_id:
                    self.httpadapter[platform_id] = platform
                else:
                    logger.debug("[HTTPAdapter] 存在没有名字的HTTPAdapter实例")
        yield event.plain_result("HTTPAdapter实例:\n" + "\n".join(list(self.httpadapter)))
