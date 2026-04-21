# AstrBot HTTP Platform 插件

## 项目介绍

AstrBot HTTP Platform 是一个为 AstrBot 提供 **HTTP / HTTPS 接入能力** 的平台适配插件。

通过该插件，外部应用可以使用标准 HTTP API 或 SSE 流式接口与 AstrBot 进行交互，适合以下场景：

## 功能特性

### 核心能力

* 支持标准 HTTP 请求响应
* 支持 SSE 流式响应
* 支持普通模式与流式模式两种调用方式
* 支持多种消息入参格式
* 支持 Bearer Token 鉴权
* 支持 CORS 跨域配置
* 支持请求超时控制
* 支持健康检查接口

## 安装方法

### 方法一：插件市场安装

1. 打开 AstrBot
2. 进入插件市场
3. 搜索 `HTTP Platform`
4. 点击安装

### 方法二：手动安装

```bash
git clone https://github.com/Li-shi-ling/astrbot_plugin_httpplatform.git
```

将插件放入 AstrBot 插件目录后，重启 AstrBot 即可。

## 配置说明

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `http_host` | 字符串 | `0.0.0.0` | HTTP 服务监听地址 |
| `http_port` | 整数 | `8080` | HTTP 服务监听端口 |
| `api_prefix` | 字符串 | `/api/v1` | API 前缀 |
| `enable_http_api` | 布尔 | `true` | 是否启用 HTTP API |
| `auth_token` | 字符串 | `""` | Bearer Token，为空表示不启用鉴权 |
| `cors_origins` | 字符串 | `*` | 允许的跨域来源，多个来源可用逗号分隔 |

## API 文档

### 基础信息

* Base URL：

```text
http://<http_host>:<http_port><api_prefix>
```

默认情况下：

```text
http://127.0.0.1:8080/api/v1
```

* 认证方式：

```text
Authorization: Bearer <auth_token>
```

* 请求体类型：

```text
application/json
```

## 1. 健康检查

### GET `/health`

用于检查 HTTP 适配器是否正常运行。

示例返回：

```json
{
  "status": "ok",
  "service": "astrbot_http_adapter",
  "timestamp": 1710000000.0,
  "pending_responses": 0,
  "version": "1.0.0"
}
```

## 2. 发送消息（标准 HTTP）

### POST `/message`

发送普通 HTTP 请求，并等待完整响应返回。

### 请求体示例

```json
{
  "message": "你好，AstrBot",
  "platform": "http_test",
  "user_id": "123456",
  "nickname": "测试用户"
}
```

### 可选字段

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` | 字符串 | 自定义会话 ID，不传时默认使用 `<platform>_<user_id>` |
| `message_id` | 字符串 | 自定义消息 ID |
| `timeout` | 整数 | 请求超时时间，单位秒 |
| `username` | 字符串 | 用户名，未传时会回退到 `nickname` |

### 标准返回示例

```json
{
  "success": true,
  "response": [
    {
      "content": {
        "type": "text",
        "data": {
          "text": "你好，很高兴见到你。"
        }
      },
      "type": "ComponentType.Plain"
    }
  ],
  "event_id": "f1d6d516-f95b-45b4-9f7f-4f80f2fef0c0",
  "session_id": "http_test_123456",
  "timestamp": 1710000000.0
}
```

> `response` 返回的是 AstrBot 组件数组，而不是单纯字符串。

## 3. 流式发送消息（SSE）

### POST `/message/stream`

发送请求后，以 SSE 方式持续接收分片响应。

返回类型：

```text
Content-Type: text/event-stream
```

### SSE 请求体示例

```json
{
  "message": "请写一段自我介绍",
  "platform": "http_test",
  "user_id": "123456",
  "nickname": "测试用户",
  "heartbeat_interval": 5
}
```

### SSE 返回示例

```text
event: connected
data: {"event_id":"xxx","session_id":"http_test_123456"}

event: message
data: {"type":"message","data":{"content":{"type":"text","data":{"text":"你好"}}},"text_type":"ComponentType.Plain"}

event: message
data: {"type":"message","data":{"content":{"type":"text","data":{"text":"，欢迎使用 AstrBot"}}},"text_type":"ComponentType.Plain"}

event: end
data: {"type":"end","data":{}}
```

### 事件说明

| 事件类型 | 说明 |
| --- | --- |
| `connected` | SSE 连接建立成功 |
| `message` | 收到一段消息分片 |
| `end` | 正常结束 |
| `timeout` | 流式请求超时结束 |
| `error` | 流式处理过程中发生错误 |

## 4. 消息输入格式

当前版本的 `message` 字段支持多种格式，便于不同客户端按自己的数据结构接入。

### 4.1 纯文本

```json
{
  "message": "你好，AstrBot"
}
```

---

### 4.2 单个组件对象

```json
{
  "message": {
    "type": "image",
    "data": {
      "url": "https://example.com/demo.png"
    }
  }
}
```

### 4.3 混合组件数组

```json
{
  "message": [
    {
      "type": "text",
      "data": {
        "text": "请描述这张图"
      }
    },
    {
      "type": "image",
      "data": {
        "url": "https://example.com/demo.png"
      }
    }
  ]
}
```

### 4.4 简写对象格式

#### 文本

```json
{
  "message": {
    "text": "hello"
  }
}
```

#### 图片

```json
{
  "message": {
    "image_url": "https://example.com/demo.png"
  }
}
```

#### 音频

```json
{
  "message": {
    "audio_url": "https://example.com/demo.mp3"
  }
}
```

#### 视频

```json
{
  "message": {
    "video_url": "https://example.com/demo.mp4"
  }
}
```

#### 文件

```json
{
  "message": {
    "file_url": "https://example.com/demo.pdf",
    "name": "demo.pdf"
  }
}
```

### 4.5 OpenAI 风格内容片段

#### 单条消息对象

```json
{
  "message": {
    "role": "user",
    "content": [
      {
        "type": "input_text",
        "text": "请分析这张图片"
      },
      {
        "type": "input_image",
        "image_url": "https://example.com/demo.png"
      }
    ]
  }
}
```

#### 内容片段数组

```json
{
  "message": [
    {
      "type": "input_text",
      "text": "帮我总结文件内容"
    },
    {
      "type": "input_file",
      "file_url": "https://example.com/demo.pdf",
      "filename": "demo.pdf"
    }
  ]
}
```

## 5. 常见组件类型

当前常用输入组件类型包括：

* `text`
* `image`
* `record`
* `video`
* `file`
* `at`
* `reply`
* `poke`
* `face`
* `share`
* `location`
* `music`
* `json`
* `node`
* `nodes`

## 6. 请求头额外数据说明

除了 JSON 请求体中的 `message`、`platform`、`user_id` 等字段之外，当前版本也会保留原始 HTTP 请求头信息，方便你在插件逻辑中读取调用方传入的附加数据。

### 处理逻辑

请求进入 HTTP 适配器后，会先读取原始请求头，并将其保存到事件对象中，主要会放到下面两个位置：

* `event.headers`
* `event.get_extra("request_headers")`

同时，适配器还会把一些常用请求信息拆分后放入 extra 字段，例如：

* `event.get_extra("request_method")`
* `event.get_extra("request_url")`
* `event.get_extra("remote_addr")`
* `event.get_extra("user_agent")`
* `event.get_extra("content_type")`
* `event.get_extra("accept")`
* `event.get_extra("request_timestamp")`
* `event.get_extra("data")`（原始 JSON 请求体）

也就是说，请求头不会参与消息组件解析本身，但会作为事件上下文的一部分完整保留下来，供插件自行读取。

### 如何添加额外数据

你可以在请求时直接添加自定义 Header，例如：

```bash
curl -X POST "http://127.0.0.1:8080/api/v1/message" \
  -H "Content-Type: application/json" \
  -H "X-User-Role: admin" \
  -H "X-Trace-Id: trace-demo-001" \
  -d "{\"message\":\"hello\",\"platform\":\"http_test\",\"user_id\":\"123456\",\"nickname\":\"tester\"}"
```

Python 示例：

```python
import requests

resp = requests.post(
    "http://127.0.0.1:8080/api/v1/message",
    headers={
        "Content-Type": "application/json",
        "X-User-Role": "admin",
        "X-Trace-Id": "trace-demo-001",
    },
    json={
        "message": "hello",
        "platform": "http_test",
        "user_id": "123456",
        "nickname": "tester",
    },
    timeout=30,
)

print(resp.json())
```

### 如何在插件中获取额外数据

在 AstrBot 插件事件处理中，可以直接从事件对象里读取：

```python
request_headers = event.get_extra("request_headers") or {}
trace_id = request_headers.get("X-Trace-Id")
user_role = request_headers.get("X-User-Role")
raw_data = event.get_extra("data") or {}
```

如果你希望直接访问原始请求头映射，也可以使用：

```python
request_headers = getattr(event, "headers", {}) or {}
trace_id = request_headers.get("X-Trace-Id")
```

一个更完整的示例：

```python
@filter.on_message_event()
async def handle_http_extra_data(event: AstrMessageEvent):
    if not event.get_extra("http_request"):
        return

    request_headers = event.get_extra("request_headers") or {}
    trace_id = request_headers.get("X-Trace-Id", "")
    user_role = request_headers.get("X-User-Role", "")
    remote_addr = event.get_extra("remote_addr", "")
    payload = event.get_extra("data") or {}

    print("trace_id:", trace_id)
    print("user_role:", user_role)
    print("remote_addr:", remote_addr)
    print("payload:", payload)
```

### 使用建议

* 业务标识类信息，建议放在自定义 Header 中，例如 `X-Trace-Id`、`X-Tenant-Id`、`X-User-Role`
* 需要参与业务消息本身的内容，建议仍然放在 JSON 请求体中
* 如果你是浏览器跨域调用，自定义 Header 是否能成功发送，还会受到 CORS 预检限制

当前插件默认允许的常见请求头包括：

* `Content-Type`
* `Authorization`
* `Accept`
* `X-Request-ID`
* `Origin`

如果你从浏览器前端跨域发送额外自定义 Header，而该 Header 不在允许列表中，就可能被浏览器拦截预检请求；脚本调用或服务端对服务端调用通常不会受这个限制。

## 使用示例

### cURL

```bash
curl -X POST "http://127.0.0.1:8080/api/v1/message" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"hello\",\"platform\":\"http_test\",\"user_id\":\"123456\",\"nickname\":\"tester\"}"
```

### Python

```python
import requests

BASE_URL = "http://127.0.0.1:8080/api/v1"

payload = {
    "message": [
        {"type": "text", "data": {"text": "请解释这张图"}},
        {"type": "image", "data": {"url": "https://example.com/demo.png"}}
    ],
    "platform": "http_test",
    "user_id": "123456",
    "nickname": "测试用户"
}

resp = requests.post(f"{BASE_URL}/message", json=payload, timeout=60)
print(resp.json())
```

### JavaScript

```javascript
const payload = {
  message: {
    role: "user",
    content: [
      { type: "input_text", text: "请总结这张图片" },
      { type: "input_image", image_url: "https://example.com/demo.png" }
    ]
  },
  platform: "http_test",
  user_id: "123456",
  nickname: "测试用户"
};

const resp = await fetch("http://127.0.0.1:8080/api/v1/message", {
  method: "POST",
  headers: {
    "Content-Type": "application/json"
  },
  body: JSON.stringify(payload)
});

console.log(await resp.json());
```

## 安全建议

* 生产环境建议配置 `auth_token`
* 对公网开放时建议使用 HTTPS
* 不建议暴露未鉴权的接口到公网
* 如需浏览器访问，请按需配置 `cors_origins`

## 常见问题

### Q：`/message` 和 `/message/stream` 的区别是什么？

* `/message`：等待完整结果后一次性返回
* `/message/stream`：以 SSE 分片方式持续返回

### Q：为什么 `response` 是数组？

因为 AstrBot 返回的是消息组件结构，而不是单一文本字段。

### Q：媒体消息一定要用 URL 吗？

不一定。当前接口支持 `url`、`file`、部分简写字段，以及 OpenAI 风格内容片段格式。  
在跨机器调用场景下，更推荐使用可访问的 URL 或可被服务端识别的安全格式。

## 贡献

欢迎提交 Issue 和 PR。

## 许可证

本项目采用 **GNU AFFERO GENERAL PUBLIC LICENSE v3**。

## 作者

* lishining
* GitHub：https://github.com/Li-shi-ling/astrbot_plugin_httpplatform
* QQ 群：1083090761

---

## AstrBot HTTP Platform

为 AstrBot 提供灵活、易接入、适合二次开发的 HTTP 接口能力。

[![Moe Counter](https://count.getloli.com/get/@li-shi-ling?theme=minecraft)](https://github.com/Li-shi-ling/astrbot_plugin_httpplatform)

