from typing import List, Optional
from dataclasses import dataclass

class Whois(object):
    server:      Optional[str]       = None
    server_info: Optional[str]       = None
    operator:    bool                = False

    secure:      bool                = False

    signon:      Optional[int]       = None
    idle:        Optional[int]       = None

    channels:    Optional[List[str]] = None

    nickname: str = ""
    username: str = ""
    hostname: str = ""
    realname: str = ""
    account:  Optional[str] = None

