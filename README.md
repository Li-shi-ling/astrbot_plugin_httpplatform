# astrbot_plugin_httpplatform

为 AstrBot 提供 HTTP / HTTPS 接入能力，支持普通请求和 SSE 流式请求。

## Features

- Expose AstrBot through HTTP APIs
- Support normal response and SSE streaming response
- Accept multiple incoming message payload formats
- Support bearer token authentication
- Support CORS configuration

## Install

### Plugin Market

Search for `HTTP Platform` in the AstrBot plugin market and install it.

### Manual

```bash
git clone https://github.com/Li-shi-ling/astrbot_plugin_httpplatform.git
```

Place the plugin in the AstrBot plugin directory and restart AstrBot.

## Config

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `http_host` | `string` | `0.0.0.0` | HTTP server bind host |
| `http_port` | `int` | `8080` | HTTP server bind port |
| `api_prefix` | `string` | `/api/v1` | API path prefix |
| `enable_http_api` | `bool` | `true` | Enable HTTP API |
| `auth_token` | `string` | `""` | Bearer token, empty means disabled |
| `cors_origins` | `string` | `*` | Allowed CORS origins, comma separated |

## API

Base URL:

```text
http://<http_host>:<http_port><api_prefix>
```

Default value:

```text
http://127.0.0.1:8080/api/v1
```

Auth header when `auth_token` is configured:

```text
Authorization: Bearer <auth_token>
```

### GET `/health`

Health check endpoint.

Example response:

```json
{
  "status": "ok",
  "service": "astrbot_http_adapter",
  "timestamp": 1710000000.0,
  "pending_responses": 0,
  "version": "1.0.0"
}
```

### POST `/message`

Send a normal HTTP request and wait for the full response.

Minimal request:

```json
{
  "message": "hello",
  "platform": "http_test",
  "user_id": "123456",
  "nickname": "tester"
}
```

Optional fields:

- `session_id`: custom session id, default `<platform>_<user_id>`
- `message_id`: custom message id
- `timeout`: request timeout in seconds, default `30`

Example response:

```json
{
  "success": true,
  "response": [
    {
      "content": {
        "type": "text",
        "data": {
          "text": "hello"
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

### POST `/message/stream`

Send a request and receive SSE events.

Example request:

```json
{
  "message": "write a short introduction",
  "platform": "http_test",
  "user_id": "123456",
  "nickname": "tester"
}
```

Response content type:

```text
text/event-stream
```

Example SSE stream:

```text
event: connected
data: {"event_id":"xxx","session_id":"http_test_123456"}

event: message
data: {"type":"message","data":{"content":{"type":"text","data":{"text":"Hello"}},"text_type":"ComponentType.Plain"}}

event: message
data: {"type":"message","data":{"content":{"type":"text","data":{"text":" world"}},"text_type":"ComponentType.Plain"}}

event: end
data: {"type":"end","data":{}}
```

## Supported Message Input Formats

`message` supports these formats:

1. Plain string
2. Single AstrBot component object
3. Mixed component array
4. Shorthand object formats
5. OpenAI-style content parts

### 1. Plain string

```json
{
  "message": "你好，AstrBot"
}
```

### 2. Single component object

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

### 3. Mixed component array

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

### 4. Shorthand object formats

Text:

```json
{
  "message": {
    "text": "hello"
  }
}
```

Image:

```json
{
  "message": {
    "image_url": "https://example.com/demo.png"
  }
}
```

Audio:

```json
{
  "message": {
    "audio_url": "https://example.com/demo.mp3"
  }
}
```

Video:

```json
{
  "message": {
    "video_url": "https://example.com/demo.mp4"
  }
}
```

File:

```json
{
  "message": {
    "file_url": "https://example.com/demo.pdf",
    "name": "demo.pdf"
  }
}
```

### 5. OpenAI-style content parts

Single message object:

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

Content parts array:

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

## Supported Component Types

Commonly supported input component types:

- `text`
- `image`
- `record`
- `video`
- `file`
- `at`
- `reply`
- `poke`
- `face`
- `share`
- `location`
- `music`
- `json`
- `node`
- `nodes`

## Examples

### cURL

```bash
curl -X POST "http://127.0.0.1:8080/api/v1/message" ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"hello\",\"platform\":\"http_test\",\"user_id\":\"123456\",\"nickname\":\"tester\"}"
```

### Python

```python
import requests

BASE_URL = "http://127.0.0.1:8080/api/v1"

payload = {
    "message": [
        {"type": "text", "data": {"text": "请解释这张图"}},
        {"type": "image", "data": {"url": "https://example.com/demo.png"}},
    ],
    "platform": "http_test",
    "user_id": "123456",
    "nickname": "tester",
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
      { type: "input_text", text: "Summarize this image" },
      { type: "input_image", image_url: "https://example.com/demo.png" }
    ]
  },
  platform: "http_test",
  user_id: "123456",
  nickname: "tester"
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

## Notes

- `message` cannot be empty
- `timeout` must be a non-negative integer
- In production, enable `auth_token` and use HTTPS
- If a media object has no explicit `type`, the plugin will try to infer it from common fields like `url`, `file`, `path`, and file suffix
