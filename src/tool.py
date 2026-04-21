import inspect
import json
from typing import Any
from urllib.parse import urlparse

from astrbot.api import logger
from astrbot.api.message_components import (
    RPS,
    At,
    AtAll,
    BaseMessageComponent,
    Contact,
    Dice,
    Face,
    File,
    Forward,
    Image,
    Json,
    Location,
    Music,
    Node,
    Nodes,
    Plain,
    Poke,
    Record,
    Reply,
    Shake,
    Share,
    Unknown,
    Video,
)

# 已有的 COMPONENT_TYPES 映射
COMPONENT_TYPES = {
    # Basic Message Segments
    "plain": Plain,
    "text": Plain,
    "image": Image,
    "record": Record,
    "video": Video,
    "file": File,
    # IM-specific Message Segments
    "face": Face,
    "at": At,
    "rps": RPS,
    "dice": Dice,
    "shake": Shake,
    "share": Share,
    "contact": Contact,
    "location": Location,
    "music": Music,
    "reply": Reply,
    "poke": Poke,
    "forward": Forward,
    "node": Node,
    "nodes": Nodes,
    "json": Json,
    "unknown": Unknown,
}

IMAGE_SUFFIXES = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".webp",
    ".bmp",
    ".svg",
}
RECORD_SUFFIXES = {".mp3", ".wav", ".ogg", ".aac", ".m4a", ".flac"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}
FILE_LIKE_KEYS = {"file", "url", "path", "name"}


def _extract_suffix(value: str) -> str:
    try:
        parsed = urlparse(value)
        path = parsed.path or value
    except Exception:
        path = value

    if "." not in path:
        return ""
    return "." + path.rsplit(".", 1)[-1].lower()


def _infer_media_type_from_value(value: str) -> str | None:
    if not value:
        return None

    suffix = _extract_suffix(value)
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in RECORD_SUFFIXES:
        return "record"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    return None


def _serialize_component_for_http(data: BaseMessageComponent) -> dict[Any, Any]:
    if isinstance(data, Plain):
        return {"type": "text", "data": {"text": data.text}}
    if isinstance(data, Node):
        return {
            "type": "node",
            "data": {
                "id": data.id,
                "name": data.name,
                "uin": data.uin,
                "content": [
                    _serialize_component_for_http(component)
                    for component in (data.content or [])
                ],
            },
        }
    if isinstance(data, Nodes):
        return {
            "type": "nodes",
            "data": {
                "nodes": [
                    _serialize_component_for_http(node) for node in (data.nodes or [])
                ],
            },
        }
    return data.toDict()


def _flatten_openai_content_parts(parts: list[Any]) -> list[Any]:
    normalized: list[Any] = []
    for part in parts:
        if isinstance(part, str):
            normalized.append({"type": "text", "data": {"text": part}})
            continue
        if not isinstance(part, dict):
            normalized.append(str(part))
            continue

        part_type = str(part.get("type", "")).lower()
        if part_type in {"text", "input_text"}:
            normalized.append(
                {"type": "text", "data": {"text": part.get("text", "")}},
            )
            continue
        if part_type in {"image", "input_image", "image_url", "input_image_url"}:
            image_url = part.get("image_url", "")
            if isinstance(image_url, dict):
                image_url = image_url.get("url", "")
            if not image_url:
                image_url = part.get("url", "")
            normalized.append({"type": "image", "data": {"url": image_url}})
            continue
        if part_type in {"audio", "input_audio", "voice"}:
            audio_url = part.get("audio_url", "") or part.get("url", "")
            normalized.append({"type": "record", "data": {"url": audio_url}})
            continue
        if part_type in {"file", "input_file"}:
            file_url = part.get("file_url", "") or part.get("url", "")
            file_name = part.get("filename", "") or part.get("name", "")
            normalized.append(
                {"type": "file", "data": {"url": file_url, "name": file_name}},
            )
            continue
        normalized.append(part)
    return normalized


def normalize_message_payload(message: Any) -> list[Any]:
    if message is None:
        return []
    if isinstance(message, BaseMessageComponent):
        return [message]
    if isinstance(message, str):
        return [message]
    if isinstance(message, list):
        normalized: list[Any] = []
        for item in message:
            normalized.extend(normalize_message_payload(item))
        return normalized
    if not isinstance(message, dict):
        return [str(message)]

    if "messages" in message and isinstance(message["messages"], list):
        return normalize_message_payload(message["messages"])
    if "segments" in message and isinstance(message["segments"], list):
        return normalize_message_payload(message["segments"])
    if "items" in message and isinstance(message["items"], list):
        return normalize_message_payload(message["items"])
    if "parts" in message and isinstance(message["parts"], list):
        return normalize_message_payload(message["parts"])
    if "content" in message and "role" in message:
        return normalize_message_payload(message["content"])
    if isinstance(message.get("content"), list):
        return normalize_message_payload(
            _flatten_openai_content_parts(message["content"])
        )
    if isinstance(message.get("content"), str) and "type" not in message:
        return [message["content"]]

    msg_type = str(message.get("type", "")).lower()
    if msg_type in {"text", "input_text"}:
        data = message.get("data")
        text = message.get("text", "")
        if text == "" and isinstance(data, dict):
            text = data.get("text", "")
        return [{"type": "text", "data": {"text": text}}]
    if msg_type in {"image_url", "input_image", "input_image_url"}:
        image_url = message.get("image_url", "")
        if isinstance(image_url, dict):
            image_url = image_url.get("url", "")
        if not image_url:
            image_url = message.get("url", "")
        return [{"type": "image", "data": {"url": image_url}}]
    if msg_type in {"audio", "input_audio", "voice"}:
        audio_url = message.get("audio_url", "") or message.get("url", "")
        return [{"type": "record", "data": {"url": audio_url}}]
    if msg_type in {"mention", "mention_user"}:
        return [
            {
                "type": "at",
                "data": {
                    "qq": message.get("user_id", message.get("id", "")),
                    "name": message.get("name", ""),
                },
            },
        ]
    if msg_type in {"mention_all", "atall"}:
        return [{"type": "at", "data": {"qq": "all"}}]
    if msg_type in {"file_url", "input_file"}:
        return [
            {
                "type": "file",
                "data": {
                    "url": message.get("url", message.get("file_url", "")),
                    "name": message.get("name", message.get("filename", "")),
                },
            },
        ]
    if msg_type in {"reply_to", "quote"}:
        return [
            {
                "type": "reply",
                "data": {"id": message.get("id", message.get("message_id", ""))},
            }
        ]

    if "type" in message:
        return [message]

    if "text" in message:
        return [{"type": "text", "data": {"text": message.get("text", "")}}]
    if "image" in message:
        return [{"type": "image", "data": {"url": message.get("image", "")}}]
    if "image_url" in message:
        return [{"type": "image", "data": {"url": message.get("image_url", "")}}]
    if "audio_url" in message:
        return [{"type": "record", "data": {"url": message.get("audio_url", "")}}]
    if "video_url" in message:
        return [{"type": "video", "data": {"file": message.get("video_url", "")}}]
    if "file_url" in message:
        return [
            {
                "type": "file",
                "data": {
                    "url": message.get("file_url", ""),
                    "name": message.get("name", ""),
                },
            },
        ]

    if FILE_LIKE_KEYS.intersection(message.keys()):
        media_value = (
            message.get("url") or message.get("file") or message.get("path") or ""
        )
        inferred_type = _infer_media_type_from_value(str(media_value))
        if inferred_type == "image":
            return [{"type": "image", "data": message}]
        if inferred_type == "record":
            return [{"type": "record", "data": message}]
        if inferred_type == "video":
            return [{"type": "video", "data": message}]
        return [{"type": "file", "data": message}]

    return [message]


# BMC类型转变为Text
def BMC2Dict(data: BaseMessageComponent) -> tuple[dict[Any, Any], str]:
    """
    将 BaseMessageComponent 对象转换为 Dict和类型字符串

    Args:
        data: BaseMessageComponent 对象

    Returns:
        tuple: (Dict, 类型字符串)
    """
    return _serialize_component_for_http(data), str(data.type)


# Dict类列表转变为BMC
def Json2BMC(data: dict[str, Any]) -> BaseMessageComponent:
    """
    将字典格式的消息数据转换为对应的 BaseMessageComponent 对象
    """

    data_type: str | None = data.get("type")

    # 如果没有 type 字段
    if not data_type:
        data_text = json.dumps(data, ensure_ascii=False)
        logger.debug(f"[Json2BMC] 未获取到data_type,data:{data_text}")
        return Plain(text=data_text)

    component_class = COMPONENT_TYPES.get(data_type.lower())

    # 未知类型
    if component_class is None:
        data_text = json.dumps(data, ensure_ascii=False)
        logger.debug(f"[Json2BMC] 未知类型:{data_text}")
        return Unknown(text=data_text)

    data_content = data.get("data") or {}

    # ================= 特殊组件处理 =================

    if component_class is Plain:
        return Plain(text=data_content.get("text", ""))

    if component_class is Image:
        return Image(
            file=data_content.get("file", ""),
            url=data_content.get("url", ""),
            path=data_content.get("path", ""),
        )

    if component_class is Record:
        return Record(
            file=data_content.get("file", ""),
            url=data_content.get("url", ""),
            path=data_content.get("path", ""),
        )

    if component_class is Video:
        return Video(
            file=(
                data_content.get("file")
                or data_content.get("url")
                or data_content.get("path", "")
            ),
            cover=data_content.get("cover", ""),
            path=data_content.get("path", ""),
        )

    if component_class is File:
        return File(
            name=data_content.get("name", ""),
            file=data_content.get("file", ""),
            url=data_content.get("url", ""),
        )

    if component_class is At:
        qq = data_content.get("qq", "")
        if qq == "all":
            return AtAll()
        return At(qq=qq, name=data_content.get("name", ""))

    if component_class is Reply:
        return Reply(
            id=data_content.get("id", ""),
            text=data_content.get("text", ""),
            qq=data_content.get("qq", 0),
        )

    if component_class is Node:
        content = data_content.get("content", [])
        parsed_content = []

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    parsed_content.append(Json2BMC(item))

        return Node(
            content=parsed_content,
            name=data_content.get("name", ""),
            uin=data_content.get("user_id", data_content.get("uin", "0")),
            id=data_content.get("id", 0),
        )

    if component_class is Nodes:
        nodes = data_content.get("nodes", [])
        parsed_nodes = []

        for node_data in nodes:
            if isinstance(node_data, dict):
                node_obj = Json2BMC(node_data)
                if isinstance(node_obj, Node):
                    parsed_nodes.append(node_obj)

        return Nodes(nodes=parsed_nodes)

    if component_class is Json:
        json_data = data_content.get("data", {})
        if isinstance(json_data, str):
            return Json(data=json_data)
        return Json(data=json.dumps(json_data, ensure_ascii=False))

    if component_class is Poke:
        return Poke(
            type=data_content.get("type", ""),
            id=data_content.get("id", 0),
            qq=data_content.get("qq", 0),
        )

    # ================= 通用安全创建 =================

    try:
        return component_class(**data_content)

    except TypeError as e:
        logger.warning(f"[Json2BMC] 参数不匹配: {component_class.__name__}, err={e}")

        # 安全参数过滤（基于 __init__ 签名）
        try:
            sig = inspect.signature(component_class.__init__)
            valid_params = set(sig.parameters.keys()) - {"self"}
            filtered = {k: v for k, v in data_content.items() if k in valid_params}

            return component_class(**filtered)

        except Exception as inner_e:
            logger.warning(f"[Json2BMC] 兜底失败，转为 Unknown: {inner_e}")
            return Unknown(text=json.dumps(data, ensure_ascii=False))


# 辅助函数：解析消息链
def Json2BMCChain(data_list: list[dict[str, Any]]) -> list[BaseMessageComponent]:
    """
    将消息链的字典列表转换为 BaseMessageComponent 对象列表

    Args:
        data_list: 消息链的字典列表

    Returns:
        List[BaseMessageComponent]: 消息组件对象列表
    """
    components = []
    for item in normalize_message_payload(data_list):
        if isinstance(item, BaseMessageComponent):
            components.append(item)
        elif isinstance(item, dict):
            components.append(Json2BMC(item))
        elif isinstance(item, str):
            components.append(Plain(text=item))
        elif item is not None:
            components.append(Plain(text=str(item)))
    return components
