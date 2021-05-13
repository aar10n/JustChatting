import json
from jc.server import message
from jc.server.message import InvalidMessageError, MessageType

from typing import Any
from websockets.legacy.protocol import WebSocketCommonProtocol

class User:
  def __init__(self, stream: Any, name: str, email: str, server: Any, conn: WebSocketCommonProtocol):
    self.stream = stream
    self.name = name
    self.email = email
    self.server = server
    self.conn = conn

  async def send(self, message: object):
    msg = json.dumps(message)
    await self.conn.send(msg)

  async def listen(self):
    async for msg in self.conn:
      try:
        obj = message.parse_message(msg)
        if obj['type'] == MessageType.TEXT:
          self.stream.log_message(self, obj['text'])
          await self.server.publish(self.stream, message.text_message(self.name, obj['text']))
      except InvalidMessageError:
        pass

