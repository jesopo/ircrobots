from typing    import List
from enum      import Enum
from base64    import b64decode, b64encode
from irctokens import build
from ircstates.numerics import *

from .matching import Responses, Response, ANY
from .contexts import ServerContext
from .params   import SASLParams, SASLUserPass, SASLSCRAM, SASLExternal
from .scram    import SCRAMContext, SCRAMAlgorithm

SASL_SCRAM_MECHANISMS = [
    "SCRAM-SHA-512",
    "SCRAM-SHA-256",
    "SCRAM-SHA-1",
]
SASL_USERPASS_MECHANISMS = SASL_SCRAM_MECHANISMS+["PLAIN"]

class SASLResult(Enum):
    NONE    = 0
    SUCCESS = 1
    FAILURE = 2
    ALREADY = 3

class SASLError(Exception):
    pass
class SASLUnknownMechanismError(SASLError):
    pass

AUTH_BYTE_MAX = 400

AUTHENTICATE_ANY = Response("AUTHENTICATE", [ANY])

NUMERICS_FAIL    = Response(ERR_SASLFAIL)
NUMERICS_INITIAL = Responses([
    ERR_SASLFAIL, ERR_SASLALREADY, RPL_SASLMECHS, ERR_SASLABORTED
])
NUMERICS_LAST    = Responses([RPL_SASLSUCCESS, ERR_SASLFAIL])

def _b64e(s: str):
    return b64encode(s.encode("utf8")).decode("ascii")

def _b64eb(s: bytes) -> str:
    # encode-from-bytes
    return b64encode(s).decode("ascii")
def _b64db(s: str) -> bytes:
    # decode-to-bytes
    return b64decode(s)

class SASLContext(ServerContext):
    async def from_params(self, params: SASLParams) -> SASLResult:
        if isinstance(params, SASLUserPass):
            return await self.userpass(params.username, params.password)
        elif isinstance(params, SASLSCRAM):
            return await self.scram(params.username, params.password)
        elif isinstance(params, SASLExternal):
            return await self.external()
        else:
            raise SASLUnknownMechanismError(
                "SASLParams given with unknown mechanism "
                f"{params.mechanism!r}")

    async def external(self) -> SASLResult:
        await self.server.send(build("AUTHENTICATE", ["EXTERNAL"]))
        line = await self.server.wait_for({
            AUTHENTICATE_ANY,
            NUMERICS_INITIAL
        })

        if line.command == "907":
            # we've done SASL already. cleanly abort
            return SASLResult.ALREADY
        elif line.command == "908":
            available = line.params[1].split(",")
            raise SASLUnknownMechanismError(
                "Server does not support SASL EXTERNAL "
                f"(it supports {available}")
        elif line.command == "AUTHENTICATE" and line.params[0] == "+":
            await self.server.send(build("AUTHENTICATE", ["+"]))

            line = await self.server.wait_for(NUMERICS_LAST)
            if line.command == "903":
                return SASLResult.SUCCESS
        return SASLResult.FAILURE

    async def plain(self, username: str, password: str) -> SASLResult:
        return await self.userpass(username, password, ["PLAIN"])

    async def scram(self, username: str, password: str) -> SASLResult:
        return await self.userpass(username, password, SASL_SCRAM_MECHANISMS)

    async def userpass(self,
            username:   str,
            password:   str,
            mechanisms: List[str]=SASL_USERPASS_MECHANISMS
            ) -> SASLResult:
        def _common(server_mechs) -> List[str]:
            mechs: List[str] = []
            for our_mech in mechanisms:
                if our_mech in server_mechs:
                    mechs.append(our_mech)

            if mechs:
                return mechs
            else:
                raise SASLUnknownMechanismError(
                    "No matching SASL mechanims. "
                    f"(we want: {mechanisms} "
                    f"server has: {server_mechs})")

        if self.server.available_caps["sasl"]:
            # CAP v3.2 tells us what mechs it supports
            available = self.server.available_caps["sasl"].split(",")
            match     = _common(available)
        else:
            # CAP v3.1 does not. pick the pick and wait for 907 to inform us of
            # what mechanisms are supported
            match     = mechanisms

        while match:
            await self.server.send(build("AUTHENTICATE", [match[0]]))
            line = await self.server.wait_for({
                AUTHENTICATE_ANY,
                NUMERICS_INITIAL
            })

            if line.command == "907":
                # we've done SASL already. cleanly abort
                return SASLResult.ALREADY
            elif line.command == "908":
                # prior to CAP v3.2 - ERR telling us which mechs are supported
                available = line.params[1].split(",")
                match     = _common(available)
                await self.server.wait_for(NUMERICS_FAIL)
            elif line.command == "AUTHENTICATE" and line.params[0] == "+":
                auth_text = ""

                if match[0] == "PLAIN":
                    auth_text = f"{username}\0{username}\0{password}"
                elif match[0].startswith("SCRAM-SHA-"):
                    auth_text = await self._scram(
                        match[0], username, password)

                if not auth_text == "+":
                    auth_text = _b64e(auth_text)

                if auth_text:
                    await self._send_auth_text(auth_text)

                line = await self.server.wait_for(NUMERICS_LAST)
                if line.command   == "903":
                    return SASLResult.SUCCESS
                elif line.command == "904":
                    match.pop(0)
            else:
                break

        return SASLResult.FAILURE

    async def _scram(self, algo_str: str,
            username: str,
            password: str) -> str:
        algo_str_prep = algo_str.replace("SCRAM-", "", 1
            ).replace("-", "").upper()
        try:
            algo = SCRAMAlgorithm(algo_str_prep)
        except ValueError:
            raise ValueError("Unknown SCRAM algorithm '%s'" % algo_str_prep)
        scram = SCRAMContext(algo, username, password)

        client_first = _b64eb(scram.client_first())
        await self._send_auth_text(client_first)
        line = await self.server.wait_for(AUTHENTICATE_ANY)

        server_first = _b64db(line.params[0])
        client_final = _b64eb(scram.server_first(server_first))
        if not client_final == "":
            await self._send_auth_text(client_final)
            line = await self.server.wait_for(AUTHENTICATE_ANY)

            server_final = _b64db(line.params[0])
            verified     = scram.server_final(server_final)
            #TODO PANIC if verified is false!
            return "+"
        else:
            return ""

    async def _send_auth_text(self, text: str):
        n = AUTH_BYTE_MAX
        chunks = [text[i:i+n] for i in range(0, len(text), n)]
        if len(chunks[-1]) == 400:
            chunks.append("+")

        for chunk in chunks:
            await self.server.send(build("AUTHENTICATE", [chunk]))
