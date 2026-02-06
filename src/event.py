from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain

if TYPE_CHECKING:
    from .Platform import HttpPlatformAdapter

class HttpMessageEvent(AstrMessageEvent):
    """Message event for HTTP platform interactions.

    This event class handles HTTP platform interactions.
    """

    def __init__(
            self,
            message_str: str,
            message_obj,
            platform_meta,
            session_id: str,
            adapter: HttpPlatformAdapter,
    ):
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._adapter = adapter

    @property
    def adapter(self) -> HttpPlatformAdapter:
        """Get the adapter instance."""
        return self._adapter

    async def send(self, message: MessageChain | None):
        """Send method for HTTP platform.

        For HTTP platform, we can send messages back to connected WebSocket clients.
        """
        if message:
            message_text = "".join([str(comp) for comp in message])
            logger.debug(f"[HTTP Platform] send() called with message: {message_text}")
            
            # Send message to all connected WebSocket clients
            await self._adapter.send_ws_message({
                "type": "bot_message",
                "content": message_text,
                "timestamp": int(self.message_obj.timestamp)
            })

    async def send_streaming(self, message_chain: MessageChain, use_fallback: bool = False):
        """Streaming send for HTTP platform.

        For HTTP platform, we can send streaming messages back to connected WebSocket clients.
        """
        message_text = "".join([str(comp) for comp in message_chain])
        logger.debug(f"[HTTP Platform] send_streaming() called with message: {message_text}")
        
        # Send streaming message to all connected WebSocket clients
        await self._adapter.send_ws_message({
            "type": "bot_message_streaming",
            "content": message_text,
            "timestamp": int(self.message_obj.timestamp)
        })

    def get_http_context(self) -> dict:
        """Get context information about the current HTTP request.

        Useful for plugins that need to know the HTTP request context.
        """
        return {
            "method": self.get_extra("method"),
            "path": self.get_extra("path"),
            "headers": self.get_extra("headers", {}),
            "body": self.get_extra("body", {}),
            "request_id": self.message_obj.message_id
        }
