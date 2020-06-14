import base64, hashlib, hmac, os
from enum import Enum
from typing import Dict

# IANA Hash Function Textual Names
# https://tools.ietf.org/html/rfc5802#section-4
# https://www.iana.org/assignments/hash-function-text-names/
# MD2 has been removed as it's unacceptably weak
class SCRAMAlgorithm(Enum):
    MD5     = "MD5"
    SHA_1   = "SHA1"
    SHA_224 = "SHA224"
    SHA_256 = "SHA256"
    SHA_384 = "SHA384"
    SHA_512 = "SHA512"

SCRAM_ERRORS = [
    "invalid-encoding",
    "extensions-not-supported", # unrecognized 'm' value
    "invalid-proof",
    "channel-bindings-dont-match",
    "server-does-support-channel-binding",
    "channel-binding-not-supported",
    "unsupported-channel-binding-type",
    "unknown-user",
    "invalid-username-encoding", # invalid utf8 or bad SASLprep
    "no-resources"
]

def _scram_nonce() -> bytes:
    return base64.b64encode(os.urandom(32))
def _scram_escape(s: bytes) -> bytes:
    return s.replace(b"=", b"=3D").replace(b",", b"=2C")
def _scram_unescape(s: bytes) -> bytes:
    return s.replace(b"=3D", b"=").replace(b"=2C", b",")
def _scram_xor(s1: bytes, s2: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(s1, s2))

class SCRAMState(Enum):
    NONE           = 0
    CLIENT_FIRST   = 1
    CLIENT_FINAL   = 2
    SUCCESS        = 3
    FAILURE        = 4
    VERIFY_FAILURE = 5

class SCRAMError(Exception):
    pass

class SCRAMContext(object):
    def __init__(self, algo: SCRAMAlgorithm,
            username: str,
            password: str):
        self._algo     = algo
        self._username = username.encode("utf8")
        self._password = password.encode("utf8")

        self.state = SCRAMState.NONE
        self.error = ""
        self.raw_error = ""

        self._client_first    = b""
        self._client_nonce    = b""

        self._salted_password = b""
        self._auth_message    = b""

    def _get_pieces(self, data: bytes) -> Dict[bytes, bytes]:
        pieces = (piece.split(b"=", 1) for piece in data.split(b","))
        return dict((piece[0], piece[1]) for piece in pieces)

    def _hmac(self, key: bytes, msg: bytes) -> bytes:
        return hmac.new(key, msg, self._algo.value).digest()
    def _hash(self, msg: bytes) -> bytes:
        return hashlib.new(self._algo.value, msg).digest()

    def _constant_time_compare(self, b1: bytes, b2: bytes):
        return hmac.compare_digest(b1, b2)

    def _fail(self, error: str):
        self.raw_error = error
        if error in SCRAM_ERRORS:
            self.error = error
        else:
            self.error = "other-error"
        self.state = SCRAMState.FAILURE

    def client_first(self) -> bytes:
        self.state = SCRAMState.CLIENT_FIRST
        self._client_nonce = _scram_nonce()
        self._client_first = b"n=%s,r=%s" % (
            _scram_escape(self._username), self._client_nonce)

        # n,,n=<username>,r=<nonce>
        return b"n,,%s" % self._client_first

    def _assert_error(self, pieces: Dict[bytes, bytes]) -> bool:
        if b"e" in pieces:
            error = pieces[b"e"].decode("utf8")
            self._fail(error)
            return True
        else:
            return False

    def server_first(self, data: bytes) -> bytes:
        self.state = SCRAMState.CLIENT_FINAL

        pieces = self._get_pieces(data)
        if self._assert_error(pieces):
            return b""

        nonce = pieces[b"r"] # server combines your nonce with it's own
        if (not nonce.startswith(self._client_nonce) or
                nonce == self._client_nonce):
            self._fail("nonce-unacceptable")
            return b""

        salt = base64.b64decode(pieces[b"s"]) # salt is b64encoded
        iterations = int(pieces[b"i"])

        salted_password = hashlib.pbkdf2_hmac(self._algo.value,
            self._password, salt, iterations, dklen=None)
        self._salted_password = salted_password

        client_key = self._hmac(salted_password, b"Client Key")
        stored_key = self._hash(client_key)

        channel = base64.b64encode(b"n,,")
        auth_noproof = b"c=%s,r=%s" % (channel, nonce)
        auth_message = b"%s,%s,%s" % (self._client_first, data, auth_noproof)
        self._auth_message = auth_message

        client_signature = self._hmac(stored_key, auth_message)
        client_proof_xor = _scram_xor(client_key, client_signature)
        client_proof = base64.b64encode(client_proof_xor)

        # c=<b64encode("n,,")>,r=<nonce>,p=<proof>
        return b"%s,p=%s" % (auth_noproof, client_proof)

    def server_final(self, data: bytes) -> bool:
        pieces = self._get_pieces(data)
        if self._assert_error(pieces):
            return False

        verifier = base64.b64decode(pieces[b"v"])

        server_key = self._hmac(self._salted_password, b"Server Key")
        server_signature = self._hmac(server_key, self._auth_message)

        if server_signature == verifier:
            self.state = SCRAMState.SUCCESS
            return True
        else:
            self.state = SCRAMState.VERIFY_FAILURE
            return False
