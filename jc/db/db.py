import asyncio
import aiomysql
import os

from aiomysql.connection import Connection
from aiomysql.cursors import Cursor
from aiomysql.pool import Pool

from jc.db.tables import TABLES


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

async def create_tables():
  env = os.getenv('ENV', 'development')
  db = f'jc_{env}'

  try:
    pool = await _create_pool()
    conn: Connection
    async with pool.acquire() as conn:
      curs: Cursor
      async with conn.cursor() as curs:
        await curs.execute(f'CREATE DATABASE IF NOT EXISTS {db};')
        await curs.execute(f'USE {db};')
        for query in TABLES:
          await curs.execute(query)
        
    pool.close()
    await pool.wait_closed()
  except:
    print('failed to setup database')
