from astrbot.api.message_components import Plain, BaseMessageComponent

def BMC2Text(data: BaseMessageComponent):
    if isinstance(data, Plain):
        return data.text
    return data
