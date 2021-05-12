import asyncio
import dotenv
import os
from jc import server

if __name__ == '__main__':
  dotenv.load_dotenv(".env")
  host = os.getenv('SERVER_HOST')
  port = int(os.getenv('SERVER_PORT'))

  server = server.Server(host, port)
  asyncio.get_event_loop().run_until_complete(server.serve())
  asyncio.get_event_loop().run_forever()
