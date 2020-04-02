from typing      import Optional
from enum        import Enum
from base64      import b64encode
from dataclasses import dataclass
from irctokens   import build

from .matching import Response, Numerics, ParamAny
from .contexts import ServerContext

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

class SASLContext(ServerContext):
    async def external(self) -> SASLResult:
        await self.server.send(build("AUTHENTICATE", ["EXTERNAL"]))
        line = await self.server.wait_for(Response("AUTHENTICATE",
            [ParamAny()], errors=["904", "907", "908"]))

        if line.command == "907":
            # we've done SASL already. cleanly abort
            return SASLResult.ALREADY
        elif line.command == "908":
            available = line.params[1].split(",")
            raise SASLUnkownMechanismError(
                "Server does not support SASL EXTERNAL "
                f"(it supports {available}")
        elif line.command == "AUTHENTICATE" and line.params[0] == "+":
            await self.server.send(build("AUTHENTICATE", ["+"]))

            line = await self.server.wait_for(Numerics(["903", "904"]))
            if line.command == "903":
                return SASLResult.SUCCESS
        return SASLResult.FAILURE

    async def userpass(self, username: str, password: str) -> SASLResult:
        # this will, in the future, offer SCRAM support

        def _common(server_mechs) -> str:
            for our_mech in SASL_USERPASS_MECHANISMS:
                if our_mech in server_mechs:
                    return our_mech
            else:
                raise SASLUnkownMechanismError(
                    "No matching SASL mechanims. "
                    f"(we have: {SASL_USERPASS_MECHANISMS} "
                    f"server has: {server_mechs})")

        if not self.server.available_caps["sasl"] is None:
            # CAP v3.2 tells us what mechs it supports
            available = self.server.available_caps["sasl"].split(",")
            match     = _common(available)
        else:
            # CAP v3.1 does not. pick the pick and wait for 907 to inform us of
            # what mechanisms are supported
            match     = SASL_USERPASS_MECHANISMS[0]

        await self.server.send(build("AUTHENTICATE", [match]))
        line = await self.server.wait_for(Response("AUTHENTICATE",
            [ParamAny()], errors=["904", "907", "908"]))

        if line.command == "907":
            # we've done SASL already. cleanly abort
            return SASLResult.ALREADY
        elif line.command == "908":
            # prior to CAP v3.2 - ERR telling us which mechs are supported
            available = line.params[1].split(",")
            match     = _common(available)

            await self.server.send(build("AUTHENTICATE", [match]))
            line = await self.server.wait_for(Response("AUTHENTICATE",
                [ParamAny()]))

        if line.command == "AUTHENTICATE" and line.params[0] == "+":
            auth_text: Optional[str] = None
            if match == "PLAIN":
                auth_text = f"{username}\0{username}\0{password}"

            if not auth_text is None:
                auth_b64 = b64encode(auth_text.encode("utf8")
                    ).decode("ascii")
                await self.server.send(build("AUTHENTICATE", [auth_b64]))

                line = await self.server.wait_for(Numerics(["903", "904"]))
                if line.command == "903":
                    return SASLResult.SUCCESS
        return SASLResult.FAILURE

