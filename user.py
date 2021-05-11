import json
from typing import Any
import message
from message import MessageType
from websockets.legacy.protocol import WebSocketCommonProtocol

class User:
  def __init__(self, name: str, email: str, server: Any, conn: WebSocketCommonProtocol):
    self.name = name
    self.email = email
    self.server = server
    self.conn = conn

  async def send(self, message: object):
    msg = json.dumps(message)
    await self.conn.send(msg)

  async def listen(self):
    msg = await self.conn.recv()
    try:
      obj = message.parse_message(msg)
      if obj['type'] == MessageType.TEXT:
        await self.server.publish(message.text_message(self.name, obj['text']))
      else:
        print(f'invalid message from {self.email}')
    except:
      pass

