"""
AstrBot HTTP Adapter 示例程序

这个示例展示如何使用 HTTP 适配器为 AstrBot 提供外部 HTTP 接口。
通过 HTTP 适配器，外部应用可以通过 HTTP/HTTPS 协议访问 AstrBot。

主要功能：
1. 启动 HTTP 服务器，提供 REST API 接口
2. 提供会话管理和统计信息
3. 完整的鉴权和安全控制
"""

import json
import sqlite3
import sys
from pathlib import Path
from types import MethodType

from astrbot.api.star import Context, Star
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.core.config.default import CONFIG_METADATA_2
from astrbot.api import logger
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
        # Register config metadata as early as possible after plugin load.
        self._register_config()
        self._http_adapter_cls = HTTPAdapter
        logger.info("[HTTPAdapter] HTTP adapter imported successfully")

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

    def _install_runtime_patches(self) -> None:
        self._install_agent_internal_traceback_patch()
        self._install_shared_preferences_sync_get_patch()

    def _install_agent_internal_traceback_patch(self) -> None:
        try:
            from astrbot.core.pipeline.process_stage.method.agent_sub_stages import (
                internal as agent_internal,
            )
        except Exception as e:
            logger.warning(
                f"[HTTPAdapter] Skip runtime patch: failed to import agent internal stage: {e}",
            )
            return

        if getattr(agent_internal, "_httpplatform_agent_error_patch_installed", False):
            return
        agent_internal._httpplatform_agent_error_patch_installed = True

        class _AgentInternalLoggerProxy:
            def __init__(self, inner):
                self._inner = inner

            def error(self, msg, *args, **kwargs):
                if (
                    isinstance(msg, str)
                    and msg.startswith("Error occurred while processing agent:")
                    and sys.exc_info()[0] is not None
                    and "exc_info" not in kwargs
                ):
                    kwargs["exc_info"] = True
                return self._inner.error(msg, *args, **kwargs)

            def __getattr__(self, name):
                return getattr(self._inner, name)

        agent_internal.logger = _AgentInternalLoggerProxy(agent_internal.logger)

    def _install_shared_preferences_sync_get_patch(self) -> None:
        try:
            from astrbot.core import sp
        except Exception as e:
            logger.warning(
                f"[HTTPAdapter] Skip runtime patch: failed to import shared preferences: {e}",
            )
            return

        if getattr(sp, "_httpplatform_sqlite_sync_get_patch_installed", False):
            return
        sp._httpplatform_sqlite_sync_get_patch_installed = True

        original_get = sp.get

        def _sqlite_get_val(
            db_path: Path,
            scope: str,
            scope_id: str,
            key: str,
        ) -> object | None:
            if not db_path.exists():
                return None

            try:
                conn = sqlite3.connect(str(db_path), timeout=1.0)
            except sqlite3.Error:
                return None

            try:
                cursor = conn.execute(
                    "SELECT value FROM preferences WHERE scope=? AND scope_id=? AND key=? LIMIT 1",
                    (scope, scope_id, key),
                )
                row = cursor.fetchone()
            except sqlite3.Error:
                return None
            finally:
                conn.close()

            if not row:
                return None

            raw = row[0]
            if raw is None:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")

            if isinstance(raw, str):
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    return None
            elif isinstance(raw, dict):
                payload = raw
            else:
                return None

            if not isinstance(payload, dict):
                return None
            return payload.get("val")

        def patched_get(self, key, default=None, scope: str | None = None, scope_id=""):
            if scope_id == "":
                scope_id = "unknown"
            if scope_id is None or key is None:
                raise ValueError(
                    "scope_id and key cannot be None when getting a specific preference.",
                )

            scope_value = scope or "unknown"
            scope_id_value = scope_id or "unknown"

            db_path_raw = getattr(getattr(self, "db_helper", None), "db_path", None)
            if db_path_raw:
                try:
                    val = _sqlite_get_val(
                        Path(db_path_raw),
                        scope_value,
                        scope_id_value,
                        key,
                    )
                    return val if val is not None else default
                except Exception:
                    pass

            try:
                return original_get(key, default, scope=scope, scope_id=scope_id)
            except RuntimeError as e:
                if "bound to a different event loop" not in str(e):
                    raise
                return default

        sp.get = MethodType(patched_get, sp)

    async def initialize(self):
        """初始化插件"""
        self._register_config()
        self._install_runtime_patches()
        logger.info("[HTTPAdapter] HTTP 适配器插件初始化完成")

    async def terminate(self):
        """终止插件"""
        self._unregister_config()
        logger.info("[HTTPAdapter] HTTP 适配器插件终止")

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
            event.set_final_call()
            logger.debug(f"[on_llm_response] StandardHTTPMessageEvent 已发送响应 (event_id: {event.event_id})")

        # 处理流式HTTP消息事件 - 统一发送结束信号
        elif isinstance(event, StreamHTTPMessageEvent):
            event.set_final_call()
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
