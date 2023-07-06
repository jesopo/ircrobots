import ssl
from dataclasses import dataclass
from typing import Optional, Tuple

@dataclass
class TLS:
    client_keypair: Optional[Tuple[str, str]] = None

# tls without verification
class TLSNoVerify(TLS):
    pass

# verify via CAs
class TLSVerifyChain(TLS):
    pass

# verify by a pinned hash
class TLSVerifyHash(TLSNoVerify):
    def __init__(self, sum: str):
        self.sum = sum.lower()
class TLSVerifySHA512(TLSVerifyHash):
    pass

def tls_context(verify: bool=True) -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx
