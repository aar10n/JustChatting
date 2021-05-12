import asyncio
import re
import websockets
import functools
from http import HTTPStatus
from websockets.datastructures import Headers
from websockets.legacy.server import HTTPResponse
from websockets.exceptions import ConnectionClosedError
from jc.server import message
from jc.server.organization import Organization
from jc.server.protocol import WebsocketProtocol
from jc.server.user import User

from typing import Any, Dict, Optional

class Server:
  UPDATE_TIMEOUT = 5

  def __init__(self, host: str, port: int):
    self.host = host
    self.port = port
    self.conn_event = asyncio.Event()
    self.orgs: Dict[str, Organization] = {}

  def serve(self) -> Any:
    def handle_req_wrapper(path, headers):
      return Server.handle_request(self, path, headers)
    def handle_conn_wrapper(ws, path):
      return Server.handle_connection(self, ws, path)
    
    print(f'starting server on port {self.port}')
    return websockets.serve(
      handle_conn_wrapper, 
      self.host, 
      self.port, 
      create_protocol=functools.partial(WebsocketProtocol, handle_req_wrapper)
    )

  async def publish(self, org: Organization, message: object):
    if org is None:
      return
    await asyncio.wait([user.send(message) for user in org.users])

  #

  # handles all http requests
  async def handle_request(self, path: str, _: Headers) -> Optional[HTTPResponse]:
    org_id = Server._validate_path(path)
    if org_id is None:
      return (HTTPStatus(404), {}, bytes())
    
    if 'init' in path:
      if org_id in self.orgs:
        # org has already been initialized
        print('org already setup')
        return (HTTPStatus(304), {}, bytes())

      try:
        await self.do_org_setup(org_id)
      finally:
        pass
      # except:
      #   return (HTTPStatus(500), {}, bytes())
      return (HTTPStatus(201), {}, bytes())
    return None

  # handles websocket connections
  async def handle_connection(self, ws: WebsocketProtocol, path: str):
    org_id = Server._validate_path(path)
    if org_id is None:
      ws.close(1002)
      return

    org = self.orgs[org_id]
    try:
      print(f'[org {org_id}] connection opened')
      user = await self.do_user_setup(ws, org)
      await user.send(message.emotes_message(org.emotes))
      await user.listen()
    except:
      pass
    finally:
      print(f'[org {org_id}] connection closed')
      if user is not None:
        org.remove_user(user)

  # performs organization set-up
  async def do_org_setup(self, org_id: str):
    print(f'setting up org {org_id}')
    org = await Organization.create(org_id)
    org.add_task(lambda org : self.update_viewer_count(org))
    self.orgs[org_id] = org
    print(f'done org setup')

  # performs user set-up
  async def do_user_setup(self, ws: WebsocketProtocol, org: Organization) -> User:
    # create an empty user so the client can receive chat and viewer
    # updates even if they haven't officially "joined" the cat
    try:
      user = User(org, None, None, self, ws)
      org.add_user(user)
      org.event.set()

      # send the viewer count
      await user.send(message.viewers_message(len(org.users)))

      # after connecting the first message from the client should
      # be a 'setup' message containing information about the user
      # connecting. Keep reading messages until a setup message is
      # received.
      async for msg in ws:
        setup = message.parse_message(msg)
        if setup['type'] == 'setup':
          user.name = setup['name']
          user.email = setup['email']
          print('user joined chat')
          break
      org.log_status(f'{setup["name"]} joined the chat')  
      return user
    except ConnectionClosedError:
      if user.name:
        org.log_status(f'{user.name} left the chat')
      org.remove_user(user)

  # updates the viewer count at a fixed rate
  async def update_viewer_count(self, org: Organization):
    print(f'[org {org.id}] starting update_viewer_count task')
    while True:
      if len(org.users) == 0:
        await org.event.wait()
        org.event.clear()
      await asyncio.sleep(self.UPDATE_TIMEOUT)
      await self.publish(message.viewers_message(len(self.users)))
  
  #

  @staticmethod
  def _validate_path(path: str) -> Optional[str]:
    if not path or path == '/':
      return None
    if re.match(r'^\/\d+(\/(init\/?)?)?$', path):
      return path.replace('/', '').replace('init', '')
    return None
