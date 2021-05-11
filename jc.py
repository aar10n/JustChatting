import asyncio
import logging
import server

logger = logging.getLogger("websockets.server")
logger.setLevel(logging.ERROR)
logger.addHandler(logging.StreamHandler())

if __name__ == '__main__':
  server = server.Server('localhost', 1234)
  asyncio.get_event_loop().run_until_complete(server.serve())
  asyncio.get_event_loop().run_forever()
