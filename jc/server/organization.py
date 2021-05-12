import asyncio
from asyncio.tasks import Task
import logging
from jc.server.logger import Logger
from jc.server.user import User

from typing import Callable, List, Set, Tuple

class Organization:
  def __init__(self):
    self.id: str
    self.event: asyncio.Event
    self.logger: Logger
    self.emotes: List[Tuple[str, str]]
    self.users: Set[User]
    self.tasks: List[Task]

  @staticmethod
  async def create(id: str):
    self = Organization()
    self.id = id
    self.event = asyncio.Event()
    self.logger = await Logger.create(id)
    self.emotes = []
    self.users = set()
    self.tasks = []
    return self

  async def close(self):
    print('closing org')
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
    assert user.org == self
    assert user.name is not None
    self.logger.log_message(user, message)

  def log_status(self, status: str):
    self.logger.log_status(status)
