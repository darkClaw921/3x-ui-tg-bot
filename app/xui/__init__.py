"""3x-ui REST API client package.

Exposes:
- ``XuiClient`` — async HTTP client with auto-login and session persistence.
- ``XuiError`` — domain error raised when the panel returns ``success=false``
  or an unexpected HTTP/JSON shape.
- ``get_xui_client()`` / ``close_xui_client()`` — singleton factory.

Submodules:
- ``app.xui.client``   — low-level HTTP client and singleton factory.
- ``app.xui.inbounds`` — operations over inbounds (list/get).
- ``app.xui.clients``  — operations over clients of an inbound
  (add/update/del/getTraffics).
- ``app.xui.links``    — vless link / subscription URL / QR PNG builders.
"""

from app.xui.client import XuiClient, XuiError, close_xui_client, get_xui_client

__all__ = [
    "XuiClient",
    "XuiError",
    "get_xui_client",
    "close_xui_client",
]
