import json
from typing import List, Tuple

"""
==== Message Types ====

--- SETUP ---
client -> server
{
  type: 'setup',
  name: string,
  email: string,
}

--- TEXT ---
client -> server
{
  type: 'text',
  text: str,
}
server -> client
{
  type: 'text',
  user: str,
  time: str,
  text: str,
}

--- EMOTES ---
server -> client
{
  type: 'emotes',
  emotes: List[Tuple[str, str]]
}

--- VIEWERS ---
server -> client
{
  type: 'viewers',
  count: int
}
"""

class InvalidMessageError(Exception):
  pass

class MessageType:
  SETUP = 'setup'     # client --> server
  TEXT = 'text'       # client <-> server
  EMOTES  = 'emotes'  # server --> client
  VIEWERS = 'viewers' # server --> client


# client message types
client_messages = {
  'setup': {
    'type': 'setup',
    'name': str,
    'email': str
  },
  'text': {
    'type': 'text',
    'text': str,
  }
}

def validate_obj(template, obj):
  for key in template:
    if key not in obj:
      return False

    value = template[key]
    if type(value) in [str, int, float, bool]:
      if value != obj[key]:
        return False
    elif type(value) == type:
      if type(obj[key]) != value:
        return False
    else:
      return False
  return True

"""
Validates a websocket message string and returns
the message as a json object. If the message is
invalid, an InvalidMessageError exception is raised.
"""
def parse_message(msg: str) -> object:
  try:
    obj = json.loads(msg)
  except:
    raise InvalidMessageError('invalid json')

  if 'type' not in obj or obj['type'] not in client_messages:
    raise InvalidMessageError('invalid or missing message type')
  if validate_obj(client_messages[obj['type']], obj):
    return obj
  return InvalidMessageError('invalid message format')

"""
Validates a websocket message string and returns
the message as a json object. If the message is
invalid or of a different type than was expected, 
an InvalidMessageError exception is raised.
"""
def expect_message(msg: str, type: str) -> object:
  obj = parse_message(msg)
  if obj['type'] != type:
    raise InvalidMessageError('invalid message type')
  return obj

#

def text_message(user: str, time: str, text: str) -> object:
  obj = {
    'type': MessageType.TEXT,
    'user': user,
    'time': time,
    'text': text
  }
  return obj

def emotes_message(emotes: List[Tuple[str, str]]) -> object:
  obj = {
    'type': MessageType.EMOTES,
    'emotes': emotes
  }
  return obj

def viewers_message(viewers: int) -> object:
  obj = {
    'type': MessageType.VIEWERS,
    'viewers': viewers
  }
  return obj
