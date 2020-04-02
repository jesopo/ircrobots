from dataclasses import dataclass
from .interface import IServer

@dataclass
class ServerContext(object):
    server: IServer
