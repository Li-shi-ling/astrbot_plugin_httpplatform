from astrbot.api.message_components import (
    Plain,
    BaseMessageComponent,
    Record,
    Image
)
import json

def BMC2Text(data: BaseMessageComponent):
    if isinstance(data, Plain):
        return data.text, "text"
    elif isinstance(data, Record):
        if data.url is None:
            return data.convert_to_base64(), "record"
        else:
            return data.url, "record_url"
    elif isinstance(data, Image):
        if data.url is None:
            return data.convert_to_base64(), "image"
        else:
            return data.url, "image_url"
    else:
        return json.dumps(data.toDict()), str(data.type)
