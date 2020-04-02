from typing import Optional
from enum import Enum
from dataclasses import dataclass

SASL_USERPASS_MECHANISMS = [
    "SCRAM-SHA-512",
    "SCRAM-SHA-256",
    "SCRAM-SHA-1",
    "PLAIN"
]

class SASLResult(Enum):
    SUCCESS = 1
    FAILURE = 2
    ALREADY = 3

class SASLError(Exception):
    pass
class SASLUnkownMechanismError(SASLError):
    pass

@dataclass
class SASLParams(object):
    mechanism: str
    username:  Optional[str] = None
    password:  Optional[str] = None
class SASLUserPass(SASLParams):
    def __init__(self, username: str, password: str):
        super().__init__("USERPASS", username, password)
class SASLExternal(SASLParams):
    def __init__(self):
        super().__init__("EXTERNAL")
