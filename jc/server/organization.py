import asyncio
from jc.db import db
from typing import List, Set, Tuple

class Organization:
  def __init__(self):
    self.id: str
    self.emotes: List[Tuple[str, str]]
    self.streams: Set

  @staticmethod
  async def create(id: str):
    self = Organization()
    self.id = id
    self.emotes = await db.get_emotes(id)
    self.streams = set()
    return self

  async def close(self):
    await asyncio.wait([stream.close() for stream in self.streams])

  def add_stream(self, stream):
    self.streams.add(stream)

  def remove_stream(self, stream):
    self.streams.remove(stream)
