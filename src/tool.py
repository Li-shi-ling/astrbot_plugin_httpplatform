from astrbot.api.message_components import BaseMessageComponent
import json

def BMC2Text(data: BaseMessageComponent):
    return json.dumps(data.toDict()), str(data.type)
