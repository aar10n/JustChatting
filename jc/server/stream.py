import asyncio
from asyncio.tasks import Task
from jc.server.logger import Logger
from jc.server.user import User
from jc.server.organization import Organization

from typing import Callable, List, Set

class Stream:
  def __init__(self):
    self.id: str
    self.org: Organization
    self.conn_event: asyncio.Event
    self.dis_event: asyncio.Event
    self.logger: Logger
    self.users: Set[User]
    self.tasks: List[Task]
    self.deleted: bool

  @staticmethod
  async def create(id: str, org: Organization):
    print('creating stream')
    self = Stream()
    self.id = id
    self.org = org
    self.conn_event = asyncio.Event()
    self.dis_event = asyncio.Event()
    self.logger = await Logger.create(id)
    self.users = set()
    self.tasks = []
    self.deleted = False
    return self

  async def close(self):
    print('closing stream')
    await asyncio.wait(
      [self.logger.close()] + 
      [task.cancel() for task in self.tasks] +
      [user.conn.close() for user in self.users]
    )

  def add_task(self, fn: Callable) -> Task:
    task = asyncio.get_event_loop().create_task(fn(self))
    self.tasks += [task]
    return task

  def add_user(self, user: User):
    self.users.add(user)

  def remove_user(self, user: User):
    self.users.remove(user)
  
  def log_message(self, user: User, message: str): 
    assert user.stream == self
    assert user.name is not None
    self.logger.log_message(user, message)

  def log_status(self, status: str):
    self.logger.log_status(status)
