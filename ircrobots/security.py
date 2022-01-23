import ssl

class TLS:
    pass

# tls without verification
class TLSNoVerify(TLS):
    pass
TLS_NOVERIFY = TLSNoVerify()

# verify via CAs
class TLSVerifyChain(TLS):
    pass
TLS_VERIFYCHAIN = TLSVerifyChain()

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
