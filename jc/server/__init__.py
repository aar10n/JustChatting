import dotenv
from jc.server import server
from jc.server import logger
dotenv.load_dotenv(".env")

Server = server.Server
