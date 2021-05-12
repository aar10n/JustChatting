import asyncio
import websockets
from websockets.legacy import protocol
from jc.server import message
from jc.server.message import MessageType
from jc.server.user import User

from typing import Any

WebsocketProtocol = protocol.WebSocketCommonProtocol


class Server:
  SETUP_TIMEOUT = 5
  UPDATE_TIMEOUT = 5

  def __init__(self, host: str, port: int):
    self.host = host
    self.port = port
    self.emotes = []
    self.users = set()
    # events
    self.conn_event = asyncio.Event()

  def serve(self) -> Any:
    print(f'starting server on port {self.port}')
    def wrapper(ws, path):
      return Server.handle_connection(self, ws, path)
    
    asyncio.get_event_loop().create_task(self.update_viewer_count())
    return websockets.serve(wrapper, self.host, self.port)

  async def publish(self, message: object):
    tasks = [user.send(message) for user in self.users]
    await asyncio.wait(tasks)

  #
  
  async def handle_setup(self, ws: WebsocketProtocol) -> User:
    # after connecting the first message from the client should
    # be a 'setup' message containing information about the user
    # connecting.
    msg = await asyncio.wait_for(ws.recv(), self.SETUP_TIMEOUT)
    setup = message.expect_message(msg, MessageType.SETUP)
    user = User(setup['name'], setup['email'], self, ws)
    self.users.add(user)
    return user


  async def handle_connection(self, ws: WebsocketProtocol, path: str):
    try:
      print('connection opened')
      user = await self.handle_setup(ws)
      self.conn_event.set()
      await user.send(message.viewers_message(len(self.users)))
      await user.send(message.emotes_message(self.emotes))
      await user.listen()
    finally:
      print('connection closed')
      self.users.remove(user)

  # updates the viewer count at a fixed rate
  async def update_viewer_count(self):
    while True:
      if len(self.users) == 0:
        await self.conn_event.wait()
        self.conn_event.clear()
      await asyncio.sleep(self.UPDATE_TIMEOUT)
      await self.publish(message.viewers_message(len(self.users)))
      