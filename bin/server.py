import asyncio
import dotenv
import os
import ssl
from jc import server

if __name__ == '__main__':
  dotenv.load_dotenv(".env")
  host = os.getenv('SERVER_HOST')
  port = int(os.getenv('SERVER_PORT'))

  crt_file = os.getenv('CRT_FILE')
  key_file = os.getenv('KEY_FILE')
  if crt_file is None or key_file is None:
    ssl_ctx = None
  else:
    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(certfile=crt_file, keyfile=key_file)

  server = server.Server(host, port, ssl_ctx)
  asyncio.get_event_loop().run_until_complete(server.serve())
  asyncio.get_event_loop().run_forever()
