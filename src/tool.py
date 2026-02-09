from astrbot.api.message_components import Plain, BaseMessageComponent, Record

def BMC2Text(data: BaseMessageComponent):
    if isinstance(data, Plain):
        return data.text, "text"
    if isinstance(data, Record):
        return data.convert_to_base64(), "record"
    return data
