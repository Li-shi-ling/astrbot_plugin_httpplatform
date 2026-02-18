---

# AstrBot HTTP Platform 插件

## 📖 项目介绍

AstrBot HTTP Platform 是一个为 AstrBot 提供 **HTTP / HTTPS 接口能力** 的平台适配器插件。

通过该插件，外部应用可以通过标准 REST API 或 SSE 流式接口与 AstrBot 交互，实现：

* 🌐 Web 应用接入
* 📱 移动端集成
* 🖥 桌面客户端对接
* 🔗 第三方系统集成
* 🎛 远程控制与自动化

---

# ✨ 功能特性

## 核心能力

* ✅ 标准 REST API
* ✅ SSE 流式响应（Server-Sent Events）
* ✅ 支持流式 / 非流式 两种调用模式
* ✅ 会话管理
* ✅ 鉴权机制（Bearer Token）
* ✅ CORS 跨域支持
* ✅ 请求日志记录
* ✅ 超时控制

## 技术特性

* 🚀 异步高性能 HTTP 服务
* 🔒 可选 Token 认证
* ⚡ 低延迟流式输出
* 📊 会话状态统计
* 🔧 灵活配置

---

# 📦 安装方法

## 方法一：插件市场安装（推荐）

1. 打开 AstrBot
2. 进入插件市场
3. 搜索 `HTTP Platform`
4. 点击安装

---

## 方法二：手动安装

```bash
git clone https://github.com/Li-shi-ling/astrbot_plugin_httpplatform.git
```

重启 AstrBot 即可。

---

# ⚙ 配置说明

| 配置项              | 类型  | 默认值      | 描述             |
| ---------------- | --- | -------- | -------------- |
| http_host        | 字符串 | 0.0.0.0  | 监听地址           |
| http_port        | 整数  | 8080     | 监听端口           |
| api_prefix       | 字符串 | /api/v1  | API 前缀         |
| enable_http_api  | 布尔  | True     | 是否启用 HTTP      |
| auth_token       | 字符串 | ""       | Bearer Token   |
| cors_origins     | 字符串 | *        | 允许跨域来源         |
| max_request_size | 整数  | 10485760 | 最大请求体（默认 10MB） |
| request_timeout  | 整数  | 30       | 请求超时（秒）        |
| session_timeout  | 整数  | 3600     | 会话超时           |
| max_sessions     | 整数  | 1000     | 最大会话数          |

---

# 📡 API 文档

## 基础信息

* Base URL:

  ```
  http://localhost:8080/api/v1
  ```

* 认证方式：

  ```
  Authorization: Bearer <auth_token>
  ```

* Content-Type:

  ```
  application/json
  ```

---

# 1️⃣ 发送消息（标准 HTTP）

### POST `/messages`

## 请求体

```json
{
  "message": "你好，AstrBot！",
  "platform": "http_test",
  "user_id": "123456",
  "nickname": "测试用户",
  "timeout": 30
}
```

---

## ✅ 标准 HTTP 返回（非流式）

```json
{
  "event_id": "05735cd0-c08e-407c-81d8-0fdc842f831f",
  "response": [
    {
      "content": {
        "type": "text",
        "data": {
          "text": "你好！很高兴再次见到你。"
        }
      },
      "type": "ComponentType.Plain"
    }
  ],
  "session_id": "http_test_123456",
  "success": true,
  "timestamp": 1771423536.5876043
}
```

> response 为组件数组，而不是字符串

---

# 2️⃣ 流式发送消息（SSE）

### POST `/messages/stream`

返回类型：

```
Content-Type: text/event-stream
```

---

## ✅ 流式模式示例（SSE）

```
event: connected
data: {"event_id":"xxx","session_id":"http_test_123456"}

event: message
data: {"type":"message","data":{"content":{"type":"text","data":{"text":"你好"}}},"text_type":"ComponentType.Plain"}

event: message
data: {"type":"message","data":{"content":{"type":"text","data":{"text":"！欢迎回来！"}}},"text_type":"ComponentType.Plain"}

event: end
data: {"type":"end","data":{}}
```

---

## 事件说明

| 事件类型      | 说明   |
| --------- | ---- |
| connected | 建立连接 |
| message   | 消息分片 |
| end       | 正常结束 |
| timeout   | 超时结束 |

---

# 3️⃣ 获取会话信息

### GET `/sessions/{session_id}`

```json
{
  "ok": true,
  "data": {
    "session_id": "http_test_123456",
    "created_at": "2024-01-01T00:00:00Z",
    "last_activity": "2024-01-01T00:00:00Z",
    "message_count": 5
  }
}
```

---

# 4️⃣ 获取会话列表

### GET `/sessions`

```json
{
  "ok": true,
  "data": [
    {
      "session_id": "uuid1",
      "created_at": "2024-01-01T00:00:00Z",
      "last_activity": "2024-01-01T00:00:00Z",
      "message_count": 5
    }
  ]
}
```

---

# 💻 使用示例

## Python

```python
import requests

BASE_URL = "http://localhost:8080/api/v1"

response = requests.post(
    f"{BASE_URL}/messages",
    json={
        "message": "你好，AstrBot！",
        "platform": "http_test",
        "user_id": "123456",
        "nickname": "测试用户"
    }
)

print(response.json())
```

---

## JavaScript

```javascript
fetch("http://localhost:8080/api/v1/messages", {
    method: "POST",
    headers: {
        "Content-Type": "application/json"
    },
    body: JSON.stringify({
        message: "你好，AstrBot！",
        platform: "http_test",
        user_id: "123456",
        nickname: "测试用户"
    })
})
.then(res => res.json())
.then(console.log);
```

---

# 🔐 安全建议

* 强烈建议配置 `auth_token`
* 生产环境务必使用 HTTPS
* 不要暴露到公网未加认证端口

---

# ❓ 常见问题

### Q: SSE 和普通 HTTP 区别？

* `/messages` → 等待完整响应返回
* `/messages/stream` → 实时返回分片

---

### Q: response 为什么是数组？

因为 AstrBot 返回的是组件结构

---

# 🤝 贡献

欢迎 PR / Issue！

---

# 📄 许可证

本项目采用 **GNU AFFERO GENERAL PUBLIC LICENSE v3**

---

# 👤 作者

* lishining
* GitHub:
  [https://github.com/Li-shi-ling/astrbot_plugin_httpplatform](https://github.com/Li-shi-ling/astrbot_plugin_httpplatform)

---

# 🚀 AstrBot HTTP Platform

为 AstrBot 提供强大而灵活的 HTTP 接口能力。
