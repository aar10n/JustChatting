from __future__ import annotations

import asyncio
import functools
import re
import websockets
from http import HTTPStatus
from ssl import SSLContext
from websockets.legacy.server import HTTPResponse
from websockets.exceptions import ConnectionClosedError

from jc.db import db
from jc.server import message
from jc.server.organization import Organization
from jc.server.stream import Stream
from jc.server.protocol import WebsocketProtocol
from jc.server.user import User

from typing import Any, Dict, Optional

def _w(self, fn):
  return functools.partial(fn, self)

class Server:
  UPDATE_TIMEOUT = 5

  def __init__(self, host: str, port: int, ssl: SSLContext = None):
    self.host = host
    self.port = port
    self.ssl = ssl
    self.conn_event = asyncio.Event()
    self.orgs: Dict[str, Organization] = {}
    self.streams: Dict[str, Stream] = {}

  def serve(self) -> Any:
    def handle_conn_wrapper(ws, path):
      return Server.handle_connection(self, ws, path)
    
    protocol_factory = WebsocketProtocol.create_factory(
      [
        ('POST', '/org/{org_id}', _w(self, Server.handle_org_setup)),
        ('PUT', '/org/{org_id}/streams/{stream_id}', _w(self, Server.handle_stream_setup)),
        ('GET', '/stream/{stream_id}', None),
        ('DELETE', '/stream/{stream_id}', _w(self, Server.handle_stream_teardown)),
        ('*', '*', _w(self, Server.handle_unknown))
      ],
      _w(self, Server.handle_pre_connection)
    )

    asyncio.get_event_loop().run_until_complete(db.create_tables())

    print(f'starting server on port {self.port}')
    return websockets.serve(
      handle_conn_wrapper, 
      self.host, 
      self.port,
      ssl=self.ssl, 
      create_protocol=protocol_factory
    )

  async def publish(self, stream: Stream, message: object):
    if stream is None:
      return
    await asyncio.wait([user.send(message) for user in stream.users])

  #

  # default route
  async def handle_unknown(self, _, __) -> HTTPResponse:
    return (HTTPStatus(404), {}, bytes())

  # POST /org/{org_id}
  async def handle_org_setup(self, req: object, params: Dict[str, str]) -> HTTPResponse:
    org_id = params['org_id']
    if org_id in self.orgs:
      return (HTTPStatus(304), {}, bytes())
    
    print(f'setting up org {org_id}')
    org = await Organization.create(org_id)
    self.orgs[org_id] = org
    return (HTTPStatus(201), {}, bytes())

  # PUT /org/{org_id}/streams/{stream_id}
  async def handle_stream_setup(self, req: object, params: Dict[str, str]) -> HTTPResponse:
    org_id = params['org_id']
    stream_id = params['stream_id']
    print(f'setting up stream {stream_id} ({org_id})')
    if org_id in self.orgs:
      org = self.orgs[org_id]
    else:
      print(f'setting up org {org_id}')
      org = await Organization.create(org_id)
      self.orgs[org_id] = org
    
    if stream_id in self.streams:
      return (HTTPStatus(304), {}, bytes())
    
    print(f'setting up stream {stream_id}')
    stream = await Stream.create(stream_id, org)
    stream.add_task(_w(self, Server.update_viewer_count))
    stream.add_task(_w(self, Server.close_deleted_stream))
    
    self.streams[stream_id] = stream
    org.add_stream(stream)
    return (HTTPStatus(201), {}, bytes())

  # DELETE /stream/{stream_id}
  async def handle_stream_teardown(self, req: object, params: Dict[str, str]) -> HTTPResponse:
    stream_id = params['stream_id']
    if stream_id not in self.streams:
      return (HTTPStatus(404), {}, bytes())
    
    print(f'tearing down stream {stream_id}')
    stream = self.streams[stream_id]
    stream.deleted = True
    return (HTTPStatus(200), {}, bytes())

  # handle pre-websocket connections
  async def handle_pre_connection(self, ws: WebsocketProtocol) -> HTTPResponse:
    # print('pre connection')
    stream_id = ws.params['stream_id']
    if not stream_id or stream_id not in self.streams:
      print('connection denied')
      return (HTTPStatus(404), {}, bytes())
    return None

  # handle websocket connections
  async def handle_connection(self, ws: WebsocketProtocol, path: str):
    stream_id = ws.params['stream_id']  
    stream = self.streams[stream_id]
    try:
      print(f'stream {stream_id} | connection opened')
      stream.conn_event.set()
      user = await self.do_user_setup(ws, stream)
      await user.listen()
    except Exception as e:
      print(e)
      pass
    finally:
      print(f'stream {stream_id} | connection closed')
      if user is not None:
        stream.remove_user(user)
        stream.dis_event.set()

  # performs user set-up
  async def do_user_setup(self, ws: WebsocketProtocol, stream: Stream) -> User:
    # create an empty user so the client can receive chat and viewer
    # updates even if they haven't officially "joined" the cat
    try:
      user = User(stream, None, None, self, ws)
      stream.add_user(user)
      stream.conn_event.set()

      # send the viewer count and emotes
      await user.send(message.viewers_message(len(stream.users)))
      await user.send(message.emotes_message(stream.org.emotes))

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
      stream.log_status(f'{setup["name"]} joined the chat')  
      return user
    except ConnectionClosedError:
      if user.name:
        stream.log_status(f'{user.name} left the chat')
      stream.remove_user(user)
      stream.dis_event.set()

  # tasks

  # updates the viewer count at a fixed rate
  async def update_viewer_count(self, stream: Stream):
    print(f'[stream {stream.id}] starting update_viewer_count task')
    while True:
        if len(stream.users) == 0:
          await stream.conn_event.wait()
          stream.conn_event.clear()
        await asyncio.sleep(self.UPDATE_TIMEOUT)
        await self.publish(stream, message.viewers_message(len(stream.users)))
  
  # closes "deleted" streams when all users disconnect
  async def close_deleted_stream(self, stream: Stream):
    print(f'[stream {stream.id}] starting close_deleted_stream task')
    while True:
      await stream.dis_event.wait()
      stream.dis_event.clear()
      if len(stream.users) == 0 and stream.deleted:
        print('closing stream')
        stream.org.remove_stream(stream)
        await stream.close()
