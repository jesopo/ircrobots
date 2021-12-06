import ssl

from typing  import Optional
from .params import ClientTLSCertificate

def tls_context(
    verify: bool=True,
    certificate: Optional[ClientTLSCertificate]=None
    ) -> ssl.SSLContext:

    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    context.options |= ssl.OP_NO_SSLv2
    context.options |= ssl.OP_NO_SSLv3
    context.options |= ssl.OP_NO_TLSv1
    context.load_default_certs()

    if verify:
        context.verify_mode = ssl.CERT_REQUIRED

    if certificate is not None:
        context.load_cert_chain(
            certificate.certfile,
            certificate.keyfile,
            certificate.password
        )

    return context
