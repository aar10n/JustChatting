import asyncio
import aiomysql
import os

from contextlib import asynccontextmanager
from aiomysql.connection import Connection
from aiomysql.cursors import Cursor
from aiomysql.pool import Pool

from jc.db.tables import TABLES

from typing import List, Tuple

def _get_db() -> str:
  env = os.getenv('ENV', 'development')
  return f'jc_{env}'

async def _create_pool(db: str = None) -> Pool:
  host = os.getenv('MYSQL_HOST', 'localhost')
  port = int(os.getenv('MYSQL_PORT', 3306))
  user = os.getenv('MYSQL_USER')
  password = os.getenv('MYSQL_PASS')
  return await aiomysql.create_pool(
    host=host, 
    port=port, 
    user=user,
    password=password,
    db=db
  )

@asynccontextmanager
async def mysql_connection(db: str=None):
  pool = await _create_pool(db)
  try:
    conn: Connection
    async with pool.acquire() as conn:
      curs: Cursor
      async with conn.cursor() as curs:
        yield conn, curs
  finally:
    pool.close()
    await pool.wait_closed()

#

async def create_tables():
  db = _get_db()
  try:
    async with mysql_connection() as (_, curs):
      await curs.execute(f'CREATE DATABASE IF NOT EXISTS {db};')
      await curs.execute(f'USE {db};')
      for query in TABLES:
        await curs.execute(query)
  except:
    print('failed to setup database')  

async def get_emotes(org_id: str) -> List[Tuple[str, str]]:
  db = _get_db()
  try:
    async with mysql_connection(db) as (_, curs):
      await curs.execute(f'SELECT name, url FROM emotes WHERE organization_id={org_id};')
      result = await curs.fetchall()
      return result
  except Exception as e:
    print('failed to get emotes')
    print(e)
    return []

async def save_emotes(org_id: str, emotes: List[Tuple[str, str]]):
  db = _get_db()
  org_id = int(org_id)
  data = [(org_id, *pair) for pair in emotes]
  try:
    async with mysql_connection(db) as (conn, curs):
      stmt = "INSERT INTO emotes (organization_id, name, url) VALUES (%s,%s,%s)"
      await curs.executemany(stmt, data)
      await conn.commit()

      await curs.execute(f'SELECT name, url FROM emotes WHERE organization_id={org_id};')
      result = await curs.fetchall()
      return result
  except Exception as e:
    print('failed to save emotes')
    raise e

async def delete_emotes(org_id: str):
  db = _get_db()
  try:
    async with mysql_connection(db) as (conn, curs):
      await curs.execute(f'DELETE FROM emotes WHERE organization_id={org_id};')
      await conn.commit()
  except Exception as e:
    print('failed to delete emotes')
    raise e
