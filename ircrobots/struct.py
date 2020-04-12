from typing import List, Optional
from dataclasses import dataclass

class Whois(object):
    server:      Optional[str]       = None
    server_info: Optional[str]       = None
    operator:    bool                = False

    secure:      bool                = False

    signon:      Optional[int]       = None
    idle:        Optional[int]       = None

    username:    Optional[str]       = None
    hostname:    Optional[str]       = None
    realname:    Optional[str]       = None
    account:     Optional[str]       = None

    channels:    Optional[List[str]] = None
