import asyncio
from http import HTTPStatus
import re
import functools
from websockets.datastructures import Headers
from websockets.legacy.http import d, read_line, read_headers
from websockets.legacy.server import HTTPResponse, WebSocketServerProtocol
from websockets.exceptions import AbortHandshake

from typing import Callable, Coroutine, Dict, List, Optional, Tuple

def add_default_headers(resp: HTTPResponse, new_headers: Dict[str, str]) -> HTTPResponse:
  headers = resp[1] or {}
  for key, value in new_headers.items():
    if key not in headers:
      headers[key] = value
  return (resp[0], headers, resp[2])

async def read_request(stream: asyncio.StreamReader) -> Tuple[str, Headers]:
  try:
    request_line = await read_line(stream)
  except EOFError as exc:
    raise EOFError('connection closed while reading HTTP request line') from exc

  try:
    method, raw_path, version = request_line.split(b" ", 2)
  except ValueError:  # not enough values to unpack (expected 3, got 1-2)
    raise ValueError(f'invalid HTTP request line: {d(request_line)}') from None
  
  if version != b'HTTP/1.1':
    raise ValueError(f'unsupported HTTP version: {d(version)}')
  path = raw_path.decode('ascii', 'surrogateescape')
  headers = await read_headers(stream)

  body = None
  body_len = headers.get('Content-Length')
  if body_len is not None:
    try:
      body = await stream.readexactly(int(body_len))
    except EOFError as exc:
      raise EOFError('connection closed while reading HTTP headers') from exc
    except Exception as exc:
      raise exc

  return method.decode("utf-8"), path.rstrip('/'), headers, body


class NoMatchError(Exception):
  pass

class NotHandledError(Exception):
  pass

class WebsocketProtocol(WebSocketServerProtocol):
  def __init__(self, routes: List[Tuple[str, str, Coroutine]], handle_request=None, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.handlers = self._parse_routes(routes)
    self.allowed_methods = set([r[0] for r in routes if r[0] != '*'])
    self.handle_request = handle_request
    self.method = ''
    self.path = ''
    self.headers = {}
    self.params = {}

  @staticmethod
  def create_factory(routes: List[Tuple[str, str, Coroutine]], handle_request=None) -> Callable:
    """
    `routes` is a list of tuples containing the method, followed by the url
    pattern, followed by the handler.
    """
    return functools.partial(WebsocketProtocol, routes, handle_request)

  async def read_http_request(self) -> Tuple[str, Headers]:
    return self.path, self.headers

  # handle routing before websocket handshake
  async def handshake(self, *args, **kwargs) -> str:
    method, path, headers, body = await read_request(self.reader)
    if method == 'OPTIONS':
      resp = self.handle_options_request(path, headers, body)
      raise AbortHandshake(*resp)

    # print(f'{method} {path}')
    for handler in self.handlers:
      try:
        resp = await handler(method, path, headers, body)
        resp = add_default_headers(resp, {
          'Access-Control-Allow-Origin': '*',
        })
        raise AbortHandshake(*resp)
      except NoMatchError:
        continue
      except NotHandledError:
        break
    
    self.method = method
    self.path = path
    self.headers = headers
    return await super().handshake(*args, **kwargs)

  async def process_request(self, path: str, request_headers: Headers) -> Optional[HTTPResponse]:
    if self.handle_request:
      return await self.handle_request(self)
    return None

  def handle_options_request(self, path, headers, body) -> HTTPResponse:
    resp_headers = {
      'Access-Control-Allow-Methods': ', '.join(self.allowed_methods),
      'Access-Control-Allow-Origin': '*',
    }
    return (HTTPStatus(204), resp_headers, bytes())

  #

  def _parse_routes(self, routes: List[Tuple[str, str, Coroutine]]) -> Tuple[List[Coroutine], Coroutine]:
    # we're not really validating the routes so
    # just write them properly :p
    route_handlers = []
    for group in routes:
      method, route, fn = group

      param_names = []
      route = route.strip().rstrip('/').replace('/', '\/')
      for match in re.finditer(r'(?<=\{)([a-zA-Z_]+)(?=\})', route):
        param_name = match.group()
        if param_name in param_names:
          raise Exception(f'duplicate route paramter "{param_name}"')
        param_names += [param_name]

      # build regex using named capture groups
      for param in param_names:
        route = route.replace(f'{{{param}}}', f'(?P<{param}>\w+)')
      
      def capture(fn, method, route, param_names):
        if route == '*':
          assert len(param_names) == 0
          regex = None
        else:
          regex = re.compile(route)

        async def handler(mthd, path, headers, body):
          if regex is not None:
            match = regex.fullmatch(path)
            if match is None:
              raise NoMatchError()
          if method != mthd and method != '*':
            raise NoMatchError()
          
          req = {
            'method': mthd,
            'path': path,
            'headers': headers,
            'body': body
          }

          params = {}
          for param in param_names:
            params[param] = match.group(param)

          self.params = params
          if fn is None:
            raise NotHandledError()
          return await fn(req, params)
        return handler
    
      route_handlers += [capture(fn, method, route, param_names)]
    return route_handlers
