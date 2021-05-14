from __future__ import annotations

import asyncio
import functools

from jc.db.emotes import BTTV_EMOTES
import json
import websockets
from http import HTTPStatus
from ssl import SSLContext
from websockets.legacy.server import HTTPResponse
from websockets.exceptions import ConnectionClosed

from jc.db import db
from jc.server import message
from jc.server.organization import Organization
from jc.server.stream import Stream
from jc.server.protocol import WebsocketProtocol
from jc.server.user import User

from typing import Any, Dict

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
        ('DELETE', '/org/{org_id}', _w(self, Server.handle_org_teardown)),
        ('PUT', '/org/{org_id}/emotes', _w(self, Server.handle_update_emotes)),
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

  # DELETE /org/{org_id}
  async def handle_org_teardown(self, req: object, params: Dict[str, str]) -> HTTPResponse:
    org_id = params['org_id']
    if org_id not in self.orgs:
      return (HTTPStatus(404), {}, bytes())

    org = self.orgs[org_id]
    print(f'tearing down org {org_id}')
    await org.close()
    await db.delete_emotes(org_id)
    return (HTTPStatus(200), {}, bytes())
    
  # PUT /org/{org_id}/emotes
  async def handle_update_emotes(self, req: object, params: Dict[str, str]) -> HTTPResponse:
    org_id = params['org_id']
    if org_id not in self.orgs:
      return (HTTPStatus(404), {}, bytes())
    org = self.orgs[org_id]

    new_emotes = []
    try:
      obj = json.loads(req['body'].decode('utf-8'))
      if isinstance(obj, list):
        for o in obj:
          if 'name' not in o or not isinstance(o['name'], str):
            raise Exception()
          elif 'url' not in o or not isinstance(o['url'], str):
            raise Exception()
          new_emotes += [(o['name'], o['url'])]
      elif isinstance(obj, object):
        if not 'default_set' in obj:
          raise Exception()
        if obj['default_set'] == 'bttv':
            new_emotes = BTTV_EMOTES
        else:
          raise Exception()
      else:
        raise Exception()
    except Exception as e:
      print(e)
      return (HTTPStatus(400), {}, bytes())
    
    try:
      if len(new_emotes) == 0:
        return (HTTPStatus(204), {}, bytes())

      emotes = await db.save_emotes(org_id, new_emotes)
      org.emotes = emotes

      msg = message.emotes_message(emotes)
      await asyncio.wait([self.publish(s, msg) for s in org.streams])
    except:
      return (HTTPStatus(500), {}, bytes())
    return (HTTPStatus(200), {}, bytes())

  # PUT /org/{org_id}/streams/{stream_id}
  async def handle_stream_setup(self, req: object, params: Dict[str, str]) -> HTTPResponse:
    org_id = params['org_id']
    stream_id = params['stream_id']
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
    user = None
    try:
      print(f'stream {stream_id} | connection opened')
      stream.conn_event.set()
      user = await self.do_user_setup(ws, stream)
      stream.log_status(f'{user.name} joined the chat')
      await user.listen()
    except ConnectionClosed:
      pass
    except Exception as e:
      print(e)
      pass
    finally:
      print(f'stream {stream_id} | connection closed')
      if user:
        if user.name:
          stream.log_status(f'{user.name} left the chat')
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
      while True:
        msg = await ws.recv()
        setup = message.parse_message(msg)
        if setup['type'] == 'setup':
          user.name = setup['name']
          user.email = setup['email']
          break
      return user
    except ConnectionClosed as e:
      stream.remove_user(user)
      stream.dis_event.set()
      raise e

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
