from astrbot.api.message_components import BaseMessageComponent
from astrbot.api.message_components import (
    Plain,
    Poke,
    Image,
    Record,
    Video,
    File,
    Face,
    At,
    AtAll,
    RPS,
    Dice,
    Shake,
    Share,
    Contact,
    Location,
    Music,
    Reply,
    Forward,
    Node,
    Nodes,
    Json,
    Unknown,
    WechatEmoji,
)
import json
from typing import Dict, Any, List
from astrbot.api import logger
import inspect

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
    "wechatemoji": WechatEmoji,
}

# BMC类型转变为Text
def BMC2Dict(data: BaseMessageComponent) -> tuple[dict[Any,Any], str]:
    """
    将 BaseMessageComponent 对象转换为 Dict和类型字符串

    Args:
        data: BaseMessageComponent 对象

    Returns:
        tuple: (Dict, 类型字符串)
    """
    return data.toDict(), str(data.type)

# Dict类列表转变为BMC
def Json2BMC(data: Dict[str, Any]) -> BaseMessageComponent:
    """
    将字典格式的消息数据转换为对应的 BaseMessageComponent 对象
    """

    data_type: str | None = data.get("type")

    # 如果没有 type 字段
    if not data_type:
        data_text = json.dumps(data, ensure_ascii=False)
        logger.info(f"[Json2BMC] 未获取到data_type,data:{data_text}")
        return Plain(text=data_text)

    component_class = COMPONENT_TYPES.get(data_type.lower())

    # 未知类型
    if component_class is None:
        data_text = json.dumps(data, ensure_ascii=False)
        logger.info(f"[Json2BMC] 未知类型:{data_text}")
        return Unknown(text=data_text)

    data_content = data.get("data") or {}

    # ================= 特殊组件处理 =================

    if component_class is Plain:
        return Plain(text=data_content.get("text", ""))

    if component_class is Image:
        return Image(
            file=data_content.get("file", ""),
            url=data_content.get("url", ""),
            path=data_content.get("path", "")
        )

    if component_class is Record:
        return Record(
            file=data_content.get("file", ""),
            url=data_content.get("url", ""),
            path=data_content.get("path", "")
        )

    if component_class is Video:
        return Video(
            file=data_content.get("file", ""),
            cover=data_content.get("cover", ""),
            path=data_content.get("path", "")
        )

    if component_class is File:
        return File(
            name=data_content.get("name", ""),
            file=data_content.get("file", ""),
            url=data_content.get("url", "")
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
            qq=data_content.get("qq", 0)
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
            id=data_content.get("id", 0)
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
            qq=data_content.get("qq", 0)
        )

    # ================= 通用安全创建 =================

    try:
        return component_class(**data_content)

    except TypeError as e:
        logger.warning(
            f"[Json2BMC] 参数不匹配: {component_class.__name__}, err={e}"
        )

        # 安全参数过滤（基于 __init__ 签名）
        try:
            sig = inspect.signature(component_class.__init__)
            valid_params = set(sig.parameters.keys()) - {"self"}
            filtered = {
                k: v for k, v in data_content.items()
                if k in valid_params
            }

            return component_class(**filtered)

        except Exception as inner_e:
            logger.warning(
                f"[Json2BMC] 兜底失败，转为 Unknown: {inner_e}"
            )
            return Unknown(
                text=json.dumps(data, ensure_ascii=False)
            )

# 辅助函数：解析消息链
def Json2BMCChain(data_list: List[Dict[str, Any]]) -> List[BaseMessageComponent]:
    """
    将消息链的字典列表转换为 BaseMessageComponent 对象列表

    Args:
        data_list: 消息链的字典列表

    Returns:
        List[BaseMessageComponent]: 消息组件对象列表
    """
    components = []
    for item in data_list:
        if isinstance(item, dict):
            components.append(Json2BMC(item))
    return components
