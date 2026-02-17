# AstrBot HTTP Platform 插件

## 项目介绍

AstrBot HTTP Platform 是一个为 AstrBot 提供 HTTP/HTTPS 接口的适配器插件，允许外部应用通过 HTTP 协议与 AstrBot 进行交互。

通过此插件，您可以：
- 构建基于 AstrBot 的 Web 应用
- 开发移动应用与 AstrBot 集成
- 实现跨平台的 AstrBot 客户端
- 为 AstrBot 添加远程控制能力

## 功能特性

### 核心功能
- ✅ 完整的 REST API 接口
- ✅ 支持标准请求和流式响应
- ✅ 会话管理和统计
- ✅ 安全的鉴权机制
- ✅ CORS 跨域支持
- ✅ 详细的请求日志

### 技术特性
- 🚀 高性能异步 HTTP 服务器
- 🔒 安全的认证机制
- 📊 会话状态管理
- ⚡ 流式响应支持
- 🔧 灵活的配置选项

## 安装方法

### 方法一：通过插件市场安装（推荐）
1. 打开 AstrBot
2. 进入插件市场
3. 搜索 "HTTP Platform"
4. 点击安装

### 方法二：手动安装
1. 克隆此仓库到 AstrBot 的插件目录：
 ```bash
 git clone https://github.com/Li-shi-ling/astrbot_plugin_httpplatform.git
 ```
2. 重启 AstrBot

## 配置说明

插件安装后，可在 AstrBot 的平台适配器配置界面中进行以下配置：

| 配置项 | 类型 | 默认值 | 描述 |
|-------|------|-------|------|
| http_host | 字符串 | 0.0.0.0 | HTTP 服务器监听地址 |
| http_port | 整数 | 8080 | HTTP 服务器监听端口 |
| api_prefix | 字符串 | /api/v1 | API 路径前缀 |
| enable_http_api | 布尔值 | True | 是否启用 HTTP API |
| auth_token | 字符串 | "" | 鉴权令牌，留空表示不启用鉴权 |
| cors_origins | 字符串 | * | CORS 允许的源，多个用逗号分隔 |
| max_request_size | 整数 | 10485760 | 最大请求体大小（字节），默认 10MB |
| request_timeout | 整数 | 30 | HTTP 请求超时时间（秒） |
| session_timeout | 整数 | 3600 | 会话超时时间（秒），默认 1 小时 |
| max_sessions | 整数 | 1000 | 最大同时连接的会话数 |

## API 文档

### 基础信息
- **基础 URL**: `http://localhost:8080/api/v1`（根据配置调整）
- **认证方式**: Bearer Token（如果配置了 auth_token）
- **Content-Type**: `application/json`

### 主要接口

#### 1. 发送消息
- **端点**: `POST /messages`
- **请求体**:
```json
{
  "message": "你好，AstrBot！",
  "platform": "http_test",
  "user_id": "123456",
  "nickname": "测试用户",
  "timeout": 30
}
```
- **响应**:
  - **流式情况下**:
```json
{
  "event_id": "e7a7a1a4-4468-48b5-95da-95b21d4710fb",
  "response": "[{\"content\": \"{\\\"type\\\": \\\"text\\\", \\\"data\\\": {\\\"text\\\": \\\"\\\\u4f60\\\\u597d\\\"}}\", \"type\": \"ComponentType.Plain\"}, {\"content\": \"{\\\"type\\\": \\\"text\\\", \\\"data\\\": {\\\"text\\\": \\\"\\\\uff01\\\\u5f88\\\\u9ad8\\\\u5174\\\\u518d\\\\u6b21\\\\u89c1\\\\u5230\\\"}}\", \"type\": \"ComponentType.Plain\"}, ...]",
  "session_id": "http_test_123456",
  "success": true,
  "timestamp": 1771328413.872187
}
```

  - **非流式情况下**:
```json
{
  "event_id": "55fda85e-332a-4b3e-b243-c82425d8ac81",
  "response": "[{\"content\": \"{\\\"type\\\": \\\"text\\\", \\\"data\\\": {\\\"text\\\": \\\"\\\\u4f60\\\\u597d\\\\uff01\\\\u5f88\\\\u9ad8\\\\u5174\\\\u518d\\\\u6b21\\\\u89c1\\\\u5230\\\\u4f60\\\\u3002\\\\u73b0\\\\u5728\\\\u662f 2026 \\\\u5e74 2 \\\\u6709\\\\u4ec0\\\\u4e48\\\\u6211\\\\u53ef\\\\u4ee5\\\\u4e3a\\\\u4f60\\\\u505a\\\\u7684\\\\u5417\\\\uff1f\\\\u65e0\\\\u8bba\\\\u662f\\\\u89e3\\\\u7b54\\\\u95ee\\\\u9898\\\\u3001\\\\u63d0\\\\u4f9b\\\\u4fe1\\\\u606f\\\\u8fd8\\\\u662f\\\\u5176\\\\u4ed6\\\\u5e2e\\\\u52a9\\\\uff0c\\\\u6211\\\\u90fd\\\\u5728\\\\u8fd9\\\\u91cc\\\\u4e3a\\\\u4f60\\\\u670d\\\\u52a1\\\\uff01\\\"}}\", \"type\": \"ComponentType.Plain\"}]",
  "session_id": "http_test_123456",
  "success": true,
  "timestamp": 1771328519.1561277
}
```

#### 2. 流式发送消息
- **端点**: `POST /messages/stream`
- **请求体**:
```json
{
  "message": "你好，AstrBot！",
  "platform": "http_test",
  "user_id": "123456",
  "nickname": "测试用户",
  "timeout": 30
}
```
- **响应**:
  - **流式情况下**:
```
event: connected
data: {"event_id": "fd0ad59a-101d-4c60-8fc5-64645374bef1", "session_id": "http_test_123456"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\u4f60\\u597d\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\uff01\\u6b22\\u8fce\\u56de\\u6765\\uff01\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\u73b0\\u5728\\u662f 2\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"026\"}}"}
...
event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\u60f3\\u548c\\u6211\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\u5206\\u4eab\\uff0c\\u6216\\u8005\\u6709\\u4ec0\\u4e48\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\u6211\\u53ef\\u4ee5\\u5e2e\\u52a9\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\u4f60\\u7684\\u5417\\uff1f\\u6211\\u5f88\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\u4e50\\u610f\\u4e3a\\u4f60\\u63d0\\u4f9b\\u652f\\u6301\"}}"}

event: stream
data: {"chunk": "{\"type\": \"text\", \"data\": {\"text\": \"\\uff01\"}}"}

event: end
data: {}
```

  - **非流式情况下**:
```
event: connected
data: {"event_id": "6747d8de-252b-44a5-ba9f-1312b87d398c", "session_id": "http_test_123456"}

event: message
data: {"content": "{\"type\": \"text\", \"data\": {\"text\": \"\\u4f60\\u597d\\uff01\\u6b22\\u8fce\\u56de\\u6765\\uff01\\u73b0\\u5728\\u662f 2026 \\u5e74 2 \\u6708 17 \\u65e5\\u665a\\u4e0a 7 \\u70b9 42 \\u5206\\uff08CST\\uff09\\u3002\\u6709\\u4ec0\\u4e48\\u65b0\\u9c9c\\u4e8b\\u60f3\\u548c\\u6211\\u5206\\u4eab\\uff0c\\u6216\\u8005\\u6709\\u4ec0\\u4e48\\u6211\\u53ef\\u4ee5\\u5e2e\\u52a9\\u4f60\\u7684\\u5417\\uff1f\\u6211\\u5f88\\u4e50\\u610f\\u4e3a\\u4f60\\u63d0\\u4f9b\\u652f\\u6301\\uff01\"}}"}

event: end
data: {}
```

#### 3. 获取会话信息
- **端点**: `GET /sessions/{session_id}`
- **响应**:
```json
{
  "ok": true,
  "data": {
    "session_id": "uuid",
    "created_at": "2024-01-01T00:00:00Z",
    "last_activity": "2024-01-01T00:00:00Z",
    "message_count": 5
  }
}
```

#### 4. 获取会话列表
- **端点**: `GET /sessions`
- **响应**:
```json
{
  "ok": true,
  "data": [
    {
      "session_id": "uuid1",
      "created_at": "2024-01-01T00:00:00Z",
      "last_activity": "2024-01-01T00:00:00Z",
      "message_count": 5
    },
    {
      "session_id": "uuid2",
      "created_at": "2024-01-01T00:00:00Z",
      "last_activity": "2024-01-01T00:00:00Z",
      "message_count": 3
    }
  ]
}
```

## 使用示例

### Python 示例

```python
import requests

# 基础配置
BASE_URL = "http://localhost:8080/api/v1"
AUTH_TOKEN = "your-auth-token"  # 如果配置了认证

headers = {
    "Content-Type": "application/json"
}

if AUTH_TOKEN:
    headers["Authorization"] = f"Bearer {AUTH_TOKEN}"

# 发送消息
response = requests.post(
    f"{BASE_URL}/messages",
    headers=headers,
    json={
        "message": "你好，AstrBot！",
        "platform": "http_test",
        "user_id": "123456",
        "nickname": "测试用户",
        "timeout": 30
    }
)

print(response.json())
```

### JavaScript 示例

```javascript
// 基础配置
const BASE_URL = "http://localhost:8080/api/v1";
const AUTH_TOKEN = "your-auth-token"; // 如果配置了认证

const headers = {
    "Content-Type": "application/json"
};

if (AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${AUTH_TOKEN}`;
}

// 发送消息
fetch(`${BASE_URL}/messages`, {
    method: "POST",
    headers: headers,
    body: JSON.stringify({
        "message": "你好，AstrBot！",
        "platform": "http_test",
        "user_id": "123456",
        "nickname": "测试用户",
        "timeout": 30
    })
})
.then(response => response.json())
.then(data => console.log(data));
```

## 常见问题

### Q: 如何确保 API 的安全性？
A: 建议配置 `auth_token` 并使用 HTTPS 协议访问。

### Q: 如何处理跨域请求？
A: 在配置中设置 `cors_origins` 为允许的域名，或使用 `*` 允许所有来源。

### Q: 如何优化性能？
A: 可以根据实际需求调整 `max_sessions` 和 `request_timeout` 等参数。

### Q: 如何查看 API 请求日志？
A: 可以在 AstrBot 的日志界面查看详细的 HTTP 请求日志。

## 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 贡献步骤
1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 打开 Pull Request

## 许可证

本项目采用 GNU AFFERO GENERAL PUBLIC LICENSE Version 3 许可证 - 详情请参阅 [LICENSE](LICENSE) 文件

## 联系方式

- 作者: lishining
- GitHub: [https://github.com/Li-shi-ling/astrbot_plugin_httpplatform](https://github.com/Li-shi-ling/astrbot_plugin_httpplatform)

## 鸣谢

感谢 AstrBot 团队提供的插件开发框架，以及所有贡献者的支持！

---

**AstrBot HTTP Platform 插件** - 为 AstrBot 提供无限可能的 HTTP 接口