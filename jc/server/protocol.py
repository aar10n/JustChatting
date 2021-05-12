from typing import Optional
from websockets.datastructures import Headers
from websockets.legacy.server import HTTPResponse, WebSocketServerProtocol

class WebsocketProtocol(WebSocketServerProtocol):
  def __init__(self, handle_request, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.handle_request = handle_request

  async def process_request(self, path: str, request_headers: Headers) -> Optional[HTTPResponse]:
    if self.handle_request:
      return await self.handle_request(path, request_headers)
    return None
