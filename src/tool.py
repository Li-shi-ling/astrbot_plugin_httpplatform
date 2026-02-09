from astrbot.api.message_components import Plain, BaseMessageComponent, Record, Image

def BMC2Text(data: BaseMessageComponent):
    if isinstance(data, Plain):
        return data.text, "text"
    if isinstance(data, Record):
        return data.convert_to_base64(), "record"
    if isinstance(data, Image):
        return data.convert_to_base64(), "image"
    return data
