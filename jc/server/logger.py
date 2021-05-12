# Logger that can output to stdout, files or a database
from __future__ import annotations

import asyncio
from asyncio.tasks import Task
import aiomysql
import aiofiles
import os
from datetime import datetime
from jc.server.user import User

from typing import List


class LoggerProtocol:
  def __init__(self, id: str):
    time = datetime.now()
    self.id = id
    self.name = f'{time.strftime("%Y%m%d%H%M%S")}_{id}'

  @staticmethod
  async def create(id: str) -> LoggerProtocol:
    return LoggerProtocol(id)

  async def close(self):
    pass

  async def log(self, _: List[str]):
    pass


class StdoutLogger(LoggerProtocol):
  async def create(id: str):
    return StdoutLogger(id)

  async def log(self, strings: List[str]):
    for string in strings:
      print(string)

class FileLogger(LoggerProtocol):
  @staticmethod
  async def create(id: str):
    self = FileLogger(id)
    self.file = await aiofiles.open(self.name + '.log', 'w')
    return self

  async def close(self):
    await self.file.close()
    self.file = None

  async def log(self, strings: List[str]):
    await self.file.writelines([f'{line}\n' for line in strings])

class MysqlLogger(LoggerProtocol):
  @staticmethod
  async def create(id: str):
    self = MysqlLogger(id)
    await self._connect_mysql()
    return self

  async def _connect_mysql(self):
    host = os.getenv('MYSQL_HOST', 'localhost')
    port = int(os.getenv('MYSQL_PORT', 3306))
    user = os.getenv('MYSQL_USER')
    password = os.getenv('MYSQL_PASS')

    try:
      conn = await aiomysql.connect(
        host=host, port=port, 
        user=user, password=password, 
        db='jc'
      )
      self.db = conn
      self.cur = await conn.cursor()
    except:
      self.db = None
      self.cur = None

  async def close(self):
    if self.db is None:
      return
    await self.cur.close()
    self.conn.close()

  async def log(self, _: List[str]):
    # print(f'[not implemented] {strings}')
    pass

#

class Logger:
  def __init__(self) -> None:
    self.org_id: str
    self.loggers: List[LoggerProtocol]
    self.queue: List[str]
    self.lock: asyncio.Lock
    self.event: asyncio.Event
    self.task: Task
  
  @staticmethod
  async def create(org_id: str) -> Logger:
    self = Logger()
    self.org_id = org_id
    
    results = await asyncio.wait([
      StdoutLogger.create(org_id),
      FileLogger.create(org_id),
      MysqlLogger.create(org_id),
    ])
    self.loggers = [res.result() for res in results[0]]
    self.queue = []
    self.lock = asyncio.Lock()
    self.event = asyncio.Event()
    self.task = asyncio.get_event_loop().create_task(self._writer_task())


    return self
  
  async def close(self):
    print('closing logger')
    await asyncio.wait(
      [self.task.cancel()] + 
      [logger.close() for logger in self.loggers]
    )

  # batch writes
  async def _writer_task(self):
    while True:
      await self.event.wait()
      self.event.clear()
      await asyncio.sleep(1)
      
      await self.lock.acquire()
      queue = self.queue.copy()
      self.queue = []
      self.lock.release()
      # log the message
      await asyncio.wait([l.log(queue) for l in self.loggers])
  
  def _log(self, type: str, msg: str):
    time = datetime.now()
    log = f'[{type}] {time.strftime("%Y-%m-%d %H:%M:%S")} | {msg}'
    while self.lock.locked():
      continue
    self.queue += [log]
    self.event.set()
  
  #

  def log_message(self, user: User, message: str): 
    self._log('message', f'{user.name}: {message}')

  def log_status(self, status: str):
    self._log('status', status)
