"""
AstrBot HTTP Adapter 示例程序

这个示例展示如何使用 HTTP 适配器为 AstrBot 提供外部 HTTP 接口。
通过 HTTP 适配器，外部应用可以通过 HTTP/HTTPS 协议访问 AstrBot。

主要功能：
1. 启动 HTTP 服务器，提供 REST API 接口
2. 提供会话管理和统计信息
3. 完整的鉴权和安全控制
"""

from astrbot.api.star import Context, Star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.api import logger
from astrbot.api.platform import register_platform_adapter
from astrbot.api.provider import LLMResponse
from .src.http_adapter import HTTPAdapter
from .src.httpmessageevent import StandardHTTPMessageEvent, StreamHTTPMessageEvent

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
            "type": "string",
            "hint": "用于 API 访问的 Bearer Token，留空表示不启用鉴权",
            "default": ""
        },
        "cors_origins": {
            "description": "CORS 允许的源",
            "type": "string",
            "hint": "CORS 允许的源，多个用逗号分隔，* 表示允许所有",
            "default": "*"
        },
    }

    _registered: bool = False

    def __init__(self, context: Context):
        super().__init__(context)
        self.httpadapter = {}

        # 导入 HTTP 适配器以注册它
        # 装饰器会自动注册适配器
        try:
            import astrbot.cli
            version = None
            if hasattr(astrbot.cli, '__version__'):
                version = astrbot.cli.__version__
            if not version:
                logger.warning("[astrbook] 没有找到astrbot版本号,使用4.14.8前的metadata注册方案")
                self.register_414()
            else:
                try:
                    # 提取版本号中的数字部分（如 4.16.0-beta -> [4,16,0]）
                    import re
                    version_parts = re.findall(r'\d+', version)
                    v1 = [int(x) for x in version_parts]
                    v2 = [int(x) for x in "4.16.0".split('.')]
                    max_len = max(len(v1), len(v2))
                    v1 += [0] * (max_len - len(v1))
                    v2 += [0] * (max_len - len(v2))
                    if v1 >= v2:
                        self.register_416()
                    else:
                        self.register_414()
                except ValueError as e:
                    logger.warning(f"[astrbook] 解析版本号失败: {version}, {e}, 使用默认的4.14.8前注册方案")
                    self.register_414()
            self._http_adapter_cls = HTTPAdapter
            logger.info("[HTTPAdapter] HTTP 适配器导入成功")
        except ImportError as e:
            logger.error(f"[HTTPAdapter] 导入 HTTP 适配器失败: {e}", exc_info=True)
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

    @staticmethod
    def register_416():
        register_platform_adapter(
            "http_adapter",  # 适配器名称
            "HTTP/HTTPS 适配器 - 提供外部 HTTP 接口访问 AstrBot",  # 描述
            default_config_tmpl={
                "http_host": "0.0.0.0",
                "http_port": 8080,
                "api_prefix": "/api/v1",
                "enable_http_api": True,
                "auth_token": "",
                "cors_origins": "*",
            },
            i18n_resources={
                "zh-CN": {
                    "http_host": {
                        "description": "HTTP 监听主机",
                        "hint": "HTTP 服务器监听的主机地址，0.0.0.0 表示所有网络接口",
                    },
                    "http_port": {
                        "description": "HTTP 监听端口",
                        "hint": "HTTP 服务器监听的端口号",
                    },
                    "api_prefix": {
                        "description": "API 路径前缀",
                        "hint": "所有 API 接口的 URL 前缀",
                    },
                    "enable_http_api": {
                        "description": "启用 HTTP API",
                        "hint": "是否启动 HTTP API 服务",
                    },
                    "auth_token": {
                        "description": "认证令牌",
                        "hint": "API 访问认证令牌，留空表示不启用认证",
                    },
                    "cors_origins": {
                        "description": "CORS 允许的源",
                        "hint": "跨域请求允许的来源，多个用逗号分隔，* 表示全部允许",
                    },
                },
                "en-US": {
                    "http_host": {
                        "description": "HTTP listen host",
                        "hint": "HTTP server listen host, 0.0.0.0 for all interfaces",
                    },
                    "http_port": {
                        "description": "HTTP listen port",
                        "hint": "HTTP server listen port",
                    },
                    "api_prefix": {
                        "description": "API path prefix",
                        "hint": "URL prefix for all API endpoints",
                    },
                    "enable_http_api": {
                        "description": "Enable HTTP API",
                        "hint": "Whether to start the HTTP API service",
                    },
                    "auth_token": {
                        "description": "Auth token",
                        "hint": "API access authentication token, leave empty to disable",
                    },
                    "cors_origins": {
                        "description": "CORS allowed origins",
                        "hint": "Allowed origins for CORS, comma separated, * for all",
                    },
                },
            },
            config_metadata={
                "http_host": {
                    "description": "HTTP 监听主机",
                    "type": "string",
                    "hint": "HTTP 服务器监听的主机地址，0.0.0.0 表示所有网络接口",
                },
                "http_port": {
                    "description": "HTTP 监听端口",
                    "type": "int",
                    "hint": "HTTP 服务器监听的端口号",
                },
                "api_prefix": {
                    "description": "API 路径前缀",
                    "type": "string",
                    "hint": "所有 API 接口的 URL 前缀",
                },
                "enable_http_api": {
                    "description": "启用 HTTP API",
                    "type": "bool",
                    "hint": "是否启动 HTTP API 服务",
                },
                "auth_token": {
                    "description": "认证令牌",
                    "type": "string",
                    "hint": "API 访问认证令牌，留空表示不启用认证",
                },
                "cors_origins": {
                    "description": "CORS 允许的源",
                    "type": "string",
                    "hint": "跨域请求允许的来源，多个用逗号分隔，* 表示全部允许",
                },
            },
        )(HTTPAdapter)

    @staticmethod
    def register_414():
        register_platform_adapter(
            "http_adapter",  # 适配器名称
            "HTTP/HTTPS 适配器 - 提供外部 HTTP 接口访问 AstrBot",  # 描述
            default_config_tmpl={
                "http_host": "0.0.0.0",
                "http_port": 8080,
                "api_prefix": "/api/v1",
                "enable_http_api": True,
                "auth_token": "",
                "cors_origins": "*",
            }
        )(HTTPAdapter)

    @filter.command_group("http")
    async def http(self, event: AstrMessageEvent):
        pass

    @http.command("获取实例")
    async def init_http_adapter(self, event: AstrMessageEvent):
        """获取所有HTTPAdapter实例并返回"""
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

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, req: LLMResponse):
        """在LLM响应后，处理消息的结束"""
        if not req.role == "assistant":
            return

        # 处理标准HTTP消息事件 - 统一发送缓存的响应
        if isinstance(event, StandardHTTPMessageEvent):
            event.setfinalcall()
            logger.debug(f"[on_llm_response] StandardHTTPMessageEvent 已发送响应 (event_id: {event.event_id})")

        # 处理流式HTTP消息事件 - 统一发送结束信号
        elif isinstance(event, StreamHTTPMessageEvent):
            event.setfinalcall()
            logger.debug(f"[on_llm_response] StreamHTTPMessageEvent 已发送结束信号 (event_id: {event.event_id})")

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=-999999)
    async def other_message(self, event: AstrMessageEvent):
        """如果在插件调用后就结束了事件，处理消息的结束"""
        if isinstance(event, StandardHTTPMessageEvent):
            if not (
                    not event.get_has_send_oper()
                    and event.is_at_or_wake_command
                    and not event.call_llm
            ):
                await event.send_response()
        elif isinstance(event, StreamHTTPMessageEvent):
            if not (
                    not event.get_has_send_oper()
                    and event.is_at_or_wake_command
                    and not event.call_llm
            ):
                await event.send_end_signal()
