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
from typing import Dict, Any, List, Union
from astrbot import logger
import inspect
from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner

# 已有的 ComponentTypes 映射
ComponentTypes = {
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
    "WechatEmoji": WechatEmoji,
}

# BMC类型转变为Text
def BMC2Text(data: BaseMessageComponent) -> tuple[str, str]:
    """
    将 BaseMessageComponent 对象转换为 JSON 字符串和类型字符串

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

    Args:
        data: 消息数据字典，格式如 {"type": "text", "data": {"text": "hello"}}
              或 {"type": "image", "data": {"file": "https://example.com/image.jpg"}}

    Returns:
        BaseMessageComponent: 对应的消息组件对象
    """
    data_type:str | None = data.get("type", None)

    # 如果没有 type 字段，直接将json转变为json
    if data_type is None:
        data_text = json.dumps(data)
        logger.info(f"[Json2BMC] 未获取到data_type,data:{data_text}")
        return Plain(text=data_text)

    # 获取对应的组件类
    component_class = ComponentTypes.get(data_type.lower())
    if component_class is None:
        # 未知类型，返回 Unknown 组件
        data_text = json.dumps(data)
        logger.info(f"[Json2BMC] 未知类型:{data_text}")
        return Unknown(text=data_text)

    # 获取消息数据
    data_content = data.get("data", {})

    # 特殊处理一些需要额外参数的组件
    if component_class == Plain:
        return Plain(text=data_content.get("text", ""))

    elif component_class == Image:
        return Image(
            file=data_content.get("file", ""),
            url=data_content.get("url", ""),
            path=data_content.get("path", "")
        )

    elif component_class == Record:
        return Record(
            file=data_content.get("file", ""),
            url=data_content.get("url", ""),
            path=data_content.get("path", "")
        )

    elif component_class == Video:
        return Video(
            file=data_content.get("file", ""),
            cover=data_content.get("cover", ""),
            path=data_content.get("path", "")
        )

    elif component_class == File:
        return File(
            name=data_content.get("name", ""),
            file=data_content.get("file", ""),
            url=data_content.get("url", "")
        )

    elif component_class == At:
        qq = data_content.get("qq", "")
        if qq == "all":
            return AtAll()
        return At(qq=qq, name=data_content.get("name", ""))

    elif component_class == Reply:
        return Reply(
            id=data_content.get("id", ""),
            text=data_content.get("text", ""),
            qq=data_content.get("qq", 0)
        )

    elif component_class == Node:
        content = data_content.get("content", [])
        # 递归处理 content 中的消息段
        if isinstance(content, list):
            parsed_content = []
            for item in content:
                if isinstance(item, dict):
                    parsed_content.append(Json2BMC(item))
            return Node(
                content=parsed_content,
                name=data_content.get("name", ""),
                uin=data_content.get("user_id", data_content.get("uin", "0")),
                id=data_content.get("id", 0)
            )
        return Node(content=[], name=data_content.get("name", ""))

    elif component_class == Nodes:
        nodes = data_content.get("nodes", [])
        parsed_nodes = []
        for node_data in nodes:
            if isinstance(node_data, dict):
                # 递归解析每个 node
                node_obj = Json2BMC(node_data)
                if isinstance(node_obj, Node):
                    parsed_nodes.append(node_obj)
        return Nodes(nodes=parsed_nodes)

    elif component_class == Json:
        json_data = data_content.get("data", {})
        if isinstance(json_data, str):
            return Json(data=json_data)
        return Json(data=json.dumps(json_data, ensure_ascii=False))

    elif component_class == Poke:
        poke_type = data_content.get("type", "")
        return Poke(
            type=poke_type,
            id=data_content.get("id", 0),
            qq=data_content.get("qq", 0)
        )

    # 对于其他组件，直接使用参数解包创建实例
    try:
        return component_class(**data_content)
    except TypeError as e:
        # 如果参数不匹配，尝试只传递必要的参数
        return component_class(**{k: v for k, v in data_content.items() if k in component_class.__fields__})

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

# 获取调用栈里面的ToolLoopAgentRunner
def find_tool_loop_agent_runner_in_callstack() -> ToolLoopAgentRunner | None:
    """
    获取当前调用栈，并在其中查找 ToolLoopAgentRunner 类的实例方法调用，
    返回找到的 ToolLoopAgentRunner 实例。

    Returns:
        ToolLoopAgentRunner: 找到的实例，如果没有找到则返回 None
    """
    # 获取当前调用栈
    current_frame = inspect.currentframe()

    try:
        # 向上遍历调用栈
        frame = current_frame.f_back
        while frame:
            # 获取当前帧的局部变量
            local_vars = frame.f_locals

            # 检查是否为实例方法（有 self 参数）
            if 'self' in local_vars:
                instance = local_vars['self']

                # 检查实例是否为 ToolLoopAgentRunner 类型
                if isinstance(instance, ToolLoopAgentRunner):
                    logger.debug(f"[find_tool_loop_agent_runner] 找到 ToolLoopAgentRunner 实例: {instance}")
                    return instance

            # 检查局部变量中是否有 ToolLoopAgentRunner 实例
            for var_name, var_value in local_vars.items():
                if isinstance(var_value, ToolLoopAgentRunner):
                    logger.debug(f"[find_tool_loop_agent_runner] 在变量 {var_name} 中找到 ToolLoopAgentRunner 实例")
                    return var_value

            # 继续向上查找
            frame = frame.f_back

        logger.debug("[find_tool_loop_agent_runner] 在调用栈中未找到 ToolLoopAgentRunner 实例")
        return None

    finally:
        # 清理帧引用以避免内存泄漏
        del current_frame
        if 'frame' in locals():
            del frame

# 更详细的获取调用栈里面的ToolLoopAgentRunner
def find_tool_loop_agent_runner_with_stack_info() -> ToolLoopAgentRunner | None:
    """
    获取当前调用栈，打印调用栈信息，并在其中查找 ToolLoopAgentRunner 类的实例方法调用，
    返回找到的 ToolLoopAgentRunner 实例。

    Returns:
        ToolLoopAgentRunner: 找到的实例，如果没有找到则返回 None
    """
    import traceback

    current_frame = inspect.currentframe()

    try:
        # 获取完整的调用栈信息（用于调试）
        stack = traceback.extract_stack()
        logger.debug("[find_tool_loop_agent_runner] 当前调用栈:")
        for i, frame_info in enumerate(stack[:-1]):  # 排除当前函数
            logger.debug(f"  {i}: {frame_info.filename}:{frame_info.lineno} in {frame_info.name}")

        # 向上遍历调用栈查找实例
        frame = current_frame.f_back
        frame_index = 0

        while frame:
            # 获取当前帧的信息
            frame_info = inspect.getframeinfo(frame)
            local_vars = frame.f_locals

            logger.debug(
                f"[find_tool_loop_agent_runner] 检查帧 {frame_index}: {frame_info.function} at {frame_info.filename}:{frame_info.lineno}")

            # 检查是否为实例方法（有 self 参数）
            if 'self' in local_vars:
                instance = local_vars['self']
                if isinstance(instance, ToolLoopAgentRunner):
                    logger.debug(f"[find_tool_loop_agent_runner] ✓ 在 self 中找到 ToolLoopAgentRunner 实例")
                    return instance
                else:
                    logger.debug(f"[find_tool_loop_agent_runner]   self 类型为: {type(instance)}")

            # 检查局部变量
            for var_name, var_value in local_vars.items():
                if var_name not in ['self', '__class__'] and isinstance(var_value, ToolLoopAgentRunner):
                    logger.debug(f"[find_tool_loop_agent_runner] ✓ 在变量 {var_name} 中找到 ToolLoopAgentRunner 实例")
                    return var_value

            frame = frame.f_back
            frame_index += 1

        logger.debug("[find_tool_loop_agent_runner] 未找到 ToolLoopAgentRunner 实例")
        return None

    finally:
        # 清理帧引用
        del current_frame
        if 'frame' in locals():
            del frame
