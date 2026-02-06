"""
AstrBot HTTP Adapter 示例程序

这个示例展示如何使用 HTTP 适配器为 AstrBot 提供外部 HTTP 接口。
通过 HTTP 适配器，外部应用可以通过 HTTP/HTTPS 协议访问 AstrBot。

主要功能：
1. 启动 HTTP 服务器，提供 REST API 接口
2. 支持 WebSocket 连接
3. 提供会话管理和统计信息
4. 完整的鉴权和安全控制
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
        "enable_websocket": {
            "description": "启用 WebSocket",
            "type": "bool",
            "hint": "是否启用 WebSocket 支持",
            "default": True
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

    def __init__(self, context: Context, config: dict):
        super().__init__(context, config)

        # 保存配置
        self.config = config

        # 导入 HTTP 适配器以注册它
        # 装饰器会自动注册适配器
        try:
            from .adapter.http_adapter import HTTPAdapter
            logger.info("[HTTPAdapter] HTTP 适配器导入成功")
        except ImportError as e:
            logger.error(f"[HTTPAdapter] 导入 HTTP 适配器失败: {e}")
            raise

        # 同时导入简单版本（可选）
        try:
            from .adapter.simple_http_adapter import SimpleHTTPAdapter
            logger.info("[HTTPAdapter] 简单 HTTP 适配器导入成功")
        except ImportError:
            logger.warning("[HTTPAdapter] 简单 HTTP 适配器未找到，跳过导入")

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


# ==================== HTTP 工具插件 ====================
class HTTPToolsPlugin(Star):
    """
    HTTP 工具插件

    这个插件提供一些用于处理 HTTP 请求的工具函数。
    可以通过 LLM 工具调用来获取 HTTP 请求信息。
    """

    def __init__(self, context: Context, config: dict):
        super().__init__(context, config)

    @filter.llm_tool(name="get_http_info")
    async def get_http_info(self, event: AstrMessageEvent):
        '''获取当前 HTTP 请求的详细信息。

        当通过 HTTP 适配器接收到请求时，此工具可以获取请求的详细信息，
        包括请求头、客户端信息等。

        返回格式化的 HTTP 请求信息。
        '''
        # 检查是否来自 HTTP 请求
        if not event.get_extra("http_request", False) and not event.get_extra("websocket", False):
            return "当前消息不是通过 HTTP 适配器接收的。"

        # 收集信息
        info_lines = []

        # 基本信息
        info_lines.append("📡 HTTP 请求信息")
        info_lines.append("=" * 50)

        # 请求类型
        if event.get_extra("http_request"):
            info_lines.append(f"🔗 请求类型: HTTP {event.get_extra('request_method', '未知')}")
        elif event.get_extra("websocket"):
            info_lines.append(f"🔗 请求类型: WebSocket")

        # 事件信息
        event_type = event.get_extra("event_type", "未知")
        event_id = event.get_extra("event_id", "未知")
        info_lines.append(f"📝 事件ID: {event_id}")
        info_lines.append(f"📋 事件类型: {event_type}")

        # 会话信息
        session_id = event.get_extra("session_id", "未知")
        info_lines.append(f"👤 会话ID: {session_id}")

        # 客户端信息
        remote_addr = event.get_extra("remote_addr")
        client_ip = event.get_extra("client_ip")
        user_agent = event.get_extra("user_agent")

        if remote_addr or client_ip:
            info_lines.append(f"🌐 客户端地址: {remote_addr or client_ip}")
        if user_agent:
            info_lines.append(f"🖥️  User-Agent: {user_agent}")

        # URL 信息
        request_url = event.get_extra("request_url")
        if request_url:
            info_lines.append(f"🔗 请求URL: {request_url}")

        # 内容类型
        content_type = event.get_extra("content_type")
        accept = event.get_extra("accept")
        if content_type:
            info_lines.append(f"📄 Content-Type: {content_type}")
        if accept:
            info_lines.append(f"📥 Accept: {accept}")

        # 请求头信息
        headers = event.get_extra("request_headers", {})
        if headers:
            info_lines.append("")
            info_lines.append("📋 请求头信息")
            info_lines.append("-" * 30)

            # 显示重要的请求头
            important_headers = [
                'Authorization', 'Content-Type', 'Accept',
                'User-Agent', 'X-Request-ID', 'X-Forwarded-For',
                'Referer', 'Origin'
            ]

            for header in important_headers:
                if header in headers:
                    value = headers[header]
                    # 隐藏敏感信息
                    if header == 'Authorization' and value.startswith('Bearer '):
                        value = 'Bearer ***' + value[-4:] if len(value) > 10 else 'Bearer ***'
                    info_lines.append(f"  {header}: {value}")

            # 显示其他请求头（最多5个）
            other_headers = [h for h in headers.keys() if h not in important_headers]
            if other_headers:
                info_lines.append("")
                info_lines.append("其他请求头:")
                for i, header in enumerate(other_headers[:5]):  # 最多显示5个
                    info_lines.append(f"  {header}: {headers[header]}")
                if len(other_headers) > 5:
                    info_lines.append(f"  ... 还有 {len(other_headers) - 5} 个请求头未显示")

        # 原始数据
        original_data = event.get_extra("original_data", {})
        if original_data and isinstance(original_data, dict):
            info_lines.append("")
            info_lines.append("📦 原始请求数据")
            info_lines.append("-" * 30)

            # 显示关键字段
            for key, value in original_data.items():
                if key == 'message':
                    info_lines.append(f"  {key}: {value[:100]}..." if len(str(value)) > 100 else f"  {key}: {value}")
                elif key == 'session_id' or key == 'user_id' or key == 'username':
                    info_lines.append(f"  {key}: {value}")

        # 检查是否支持流式传输
        if event.get_extra("streaming", False):
            info_lines.append("")
            info_lines.append("⚡ 此请求支持流式传输")

        info_lines.append("=" * 50)

        return "\n".join(info_lines)

    @filter.llm_tool(name="http_ping")
    async def http_ping(self, event: AstrMessageEvent, message: str = "ping"):
        '''发送一个简单的 HTTP 测试响应。

        参数:
            message(string): 要返回的消息内容，默认为 "ping"

        返回一个简单的响应，用于测试 HTTP 适配器是否正常工作。
        '''
        return f"HTTP 适配器测试成功！\n消息: {message}\n时间: {event.message_obj.timestamp}"

    @filter.llm_tool(name="echo_headers")
    async def echo_headers(self, event: AstrMessageEvent, header_name: str = None):
        '''回显特定的请求头信息。

        参数:
            header_name(string, 可选): 要查看的请求头名称，如果未指定则显示所有

        返回指定请求头的值或所有请求头信息。
        '''
        headers = event.get_extra("request_headers", {})

        if not headers:
            return "未找到请求头信息。"

        if header_name:
            if header_name in headers:
                value = headers[header_name]
                # 隐藏敏感信息
                if header_name == 'Authorization' and value.startswith('Bearer '):
                    value = 'Bearer ***' + value[-4:] if len(value) > 10 else 'Bearer ***'
                return f"请求头 '{header_name}': {value}"
            else:
                available_headers = ', '.join(sorted(headers.keys()))
                return f"未找到请求头 '{header_name}'。\n可用的请求头: {available_headers}"
        else:
            result = ["所有请求头信息:"]
            for key, value in sorted(headers.items()):
                # 隐藏敏感信息
                if key == 'Authorization' and value.startswith('Bearer '):
                    value = 'Bearer ***' + value[-4:] if len(value) > 10 else 'Bearer ***'
                result.append(f"  {key}: {value}")
            return "\n".join(result)

    async def initialize(self):
        """初始化插件"""
        logger.info("[HTTPTools] HTTP 工具插件初始化完成")

    async def terminate(self):
        """终止插件"""
        logger.info("[HTTPTools] HTTP 工具插件终止")


# ==================== HTTP API 示例插件 ====================
class HTTPExamplePlugin(Star):
    """
    HTTP API 示例插件

    这个插件展示如何通过 HTTP 适配器提供的接口与外部应用交互。
    提供一些示例工具，展示 HTTP 适配器的使用场景。
    """

    def __init__(self, context: Context, config: dict):
        super().__init__(context, config)

        # 存储 HTTP 请求的统计信息
        self.request_stats = {
            "total_requests": 0,
            "successful_responses": 0,
            "failed_responses": 0,
            "last_request_time": None,
            "unique_users": set(),
            "user_agents": set()
        }

    @filter.llm_tool(name="http_stats")
    async def http_stats(self, event: AstrMessageEvent):
        '''显示 HTTP 请求的统计信息。

        收集和显示通过 HTTP 适配器接收到的请求统计信息。
        包括总请求数、成功率、用户信息等。
        '''
        # 更新统计信息
        self.request_stats["total_requests"] += 1
        self.request_stats["last_request_time"] = event.message_obj.timestamp

        # 记录用户信息
        user_id = event.get_extra("original_data", {}).get("user_id") or event.message_obj.sender.user_id
        if user_id:
            self.request_stats["unique_users"].add(user_id)

        # 记录 User-Agent
        user_agent = event.get_extra("user_agent")
        if user_agent:
            self.request_stats["user_agents"].add(user_agent)

        # 构建统计信息
        stats_lines = []
        stats_lines.append("📊 HTTP 请求统计信息")
        stats_lines.append("=" * 50)

        # 基本信息
        stats_lines.append(f"📈 总请求数: {self.request_stats['total_requests']}")
        stats_lines.append(f"✅ 成功响应: {self.request_stats['successful_responses']}")
        stats_lines.append(f"❌ 失败响应: {self.request_stats['failed_responses']}")

        # 计算成功率
        if self.request_stats['total_requests'] > 0:
            success_rate = (self.request_stats['successful_responses'] / self.request_stats['total_requests']) * 100
            stats_lines.append(f"📊 成功率: {success_rate:.2f}%")
        else:
            stats_lines.append("📊 成功率: 0.00%")

        # 用户信息
        stats_lines.append(f"👥 独立用户数: {len(self.request_stats['unique_users'])}")
        stats_lines.append(f"🖥️  User-Agent 种类: {len(self.request_stats['user_agents'])}")

        # 最后请求时间
        last_time = self.request_stats["last_request_time"]
        if last_time:
            from datetime import datetime
            dt = datetime.fromtimestamp(last_time)
            stats_lines.append(f"🕒 最后请求时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")

        # 显示前5个用户
        if self.request_stats['unique_users']:
            stats_lines.append("")
            stats_lines.append("👤 最近活跃用户:")
            users_list = list(self.request_stats['unique_users'])
            for i, user in enumerate(users_list[:5]):  # 显示前5个
                stats_lines.append(f"  {i + 1}. {user}")
            if len(users_list) > 5:
                stats_lines.append(f"  ... 还有 {len(users_list) - 5} 个用户")

        stats_lines.append("=" * 50)

        # 标记本次为成功响应
        self.request_stats["successful_responses"] += 1

        return "\n".join(stats_lines)

    @filter.llm_tool(name="http_echo")
    async def http_echo(self, event: AstrMessageEvent, format: str = "text"):
        '''回显接收到的 HTTP 请求信息。

        参数:
            format(string): 返回格式，可选 "text" 或 "json"，默认为 "text"

        回显接收到的消息和相关信息，用于调试和测试。
        '''
        original_message = event.message_str
        session_id = event.get_extra("session_id", "未知")
        user_id = event.message_obj.sender.user_id
        username = event.message_obj.sender.nickname

        response_data = {
            "status": "success",
            "message": "请求已接收并处理",
            "echo": original_message,
            "session_id": session_id,
            "user_id": user_id,
            "username": username,
            "timestamp": event.message_obj.timestamp,
            "received_via": "HTTP 适配器"
        }

        # 添加额外信息
        if event.get_extra("http_request"):
            response_data["request_type"] = "HTTP"
            response_data["request_method"] = event.get_extra("request_method")
        elif event.get_extra("websocket"):
            response_data["request_type"] = "WebSocket"

        if format.lower() == "json":
            import json
            return json.dumps(response_data, ensure_ascii=False, indent=2)
        else:
            # 文本格式
            lines = []
            lines.append("🔄 请求回显")
            lines.append("=" * 40)
            lines.append(f"📝 原始消息: {original_message}")
            lines.append(f"👤 用户: {username} ({user_id})")
            lines.append(f"🔗 会话ID: {session_id}")
            lines.append(f"📡 请求类型: {response_data.get('request_type', '未知')}")
            if 'request_method' in response_data:
                lines.append(f"⚡ 请求方法: {response_data['request_method']}")
            lines.append(f"🕒 时间戳: {response_data['timestamp']}")
            lines.append("=" * 40)
            return "\n".join(lines)

    @filter.llm_tool(name="http_calculator")
    async def http_calculator(self, event: AstrMessageEvent, expression: str):
        '''一个简单的计算器，通过 HTTP 调用。

        参数:
            expression(string): 数学表达式，例如 "2 + 3 * 4"

        计算数学表达式并返回结果。支持基本运算符：+ - * / % **
        注意：出于安全考虑，只能计算简单的数学表达式。
        '''
        # 安全过滤：只允许数学表达式中的字符
        import re
        safe_pattern = r'^[\d\s\+\-\*\/\%\.\(\)\^]+$'

        if not re.match(safe_pattern, expression):
            return "错误：表达式包含不安全字符。只允许数字、空格和基本运算符 (+ - * / % ^)。"

        try:
            # 替换 ^ 为 **（指数运算）
            expression = expression.replace('^', '**')

            # 使用 eval 计算表达式（已进行安全过滤）
            result = eval(expression, {"__builtins__": None}, {})

            # 构建响应
            response = f"""
🧮 计算器结果
═══════════════════════════════════════
📝 表达式: {expression}
🔢 结果: {result}
🔍 类型: {type(result).__name__}
═══════════════════════════════════════
注意：此计算器仅支持基本数学运算。
            """

            # 记录成功响应
            self.request_stats["successful_responses"] += 1

            return response.strip()

        except ZeroDivisionError:
            self.request_stats["failed_responses"] += 1
            return "错误：除数不能为零。"
        except SyntaxError:
            self.request_stats["failed_responses"] += 1
            return "错误：表达式语法无效。"
        except Exception as e:
            self.request_stats["failed_responses"] += 1
            return f"错误：计算失败 - {str(e)}"

    async def initialize(self):
        """初始化插件"""
        logger.info("[HTTPExample] HTTP 示例插件初始化完成")

    async def terminate(self):
        """终止插件"""
        logger.info("[HTTPExample] HTTP 示例插件终止")
