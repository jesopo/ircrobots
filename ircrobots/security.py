import ssl

def tls_context(verify: bool=True) -> ssl.SSLContext:
    return ssl.create_default_context()
