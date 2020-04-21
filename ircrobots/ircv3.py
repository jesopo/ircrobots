from time        import time
from typing      import Dict, Iterable, List, Optional, Tuple
from dataclasses import dataclass
from irctokens   import build
from ircstates.server import ServerDisconnectedException

from .contexts  import ServerContext
from .matching  import Response, ResponseOr, ParamAny
from .interface import ICapability
from .params    import ConnectionParams, STSPolicy

class Capability(ICapability):
    def __init__(self,
            ratified_name: Optional[str],
            draft_name:    Optional[str]=None,
            alias:         Optional[str]=None,
            depends_on:    List[str]=[]):
        self.name  = ratified_name
        self.draft = draft_name
        self.alias = alias or ratified_name
        self.depends_on = depends_on.copy()

        self._caps = [ratified_name, draft_name]

    def match(self, capability: str) -> bool:
        return capability in self._caps

    def available(self, capabilities: Iterable[str]
            ) -> Optional[str]:
        for cap in self._caps:
            if not cap is None and cap in capabilities:
                return cap
        else:
            return None

    def copy(self):
        return Capability(
            self.name,
            self.draft,
            alias=self.alias,
            depends_on=self.depends_on[:])

CAP_SASL  = Capability("sasl")
CAP_ECHO  = Capability("echo-message")
CAP_LABEL = Capability("labeled-response", "draft/labeled-response-0.2")
CAP_STS   = Capability("sts", "draft/sts")

LABEL_TAG = {
    "draft/labeled-response-0.2": "draft/label",
    "labeled-response": "label"
}

CAPS: List[ICapability] = [
    Capability("multi-prefix"),
    Capability("chghost"),
    Capability("away-notify"),

    Capability("invite-notify"),
    Capability("account-tag"),
    Capability("account-notify"),
    Capability("extended-join"),

    Capability("message-tags", "draft/message-tags-0.2"),
    Capability("cap-notify"),
    Capability("batch"),

    Capability(None, "draft/rename", alias="rename"),
    Capability("setname", "draft/setname")
]

def _cap_dict(s: str) -> Dict[str, str]:
    d: Dict[str, str] = {}
    for token in s.split(","):
        key, _, value = token.partition("=")
        d[key] = value
    return d

async def sts_transmute(params: ConnectionParams):
    if not params.sts is None and not params.tls:
        now   = time()
        since = (now-params.sts.created)
        if since <= params.sts.duration:
            params.port = params.sts.port
            params.tls  = True

class CAPContext(ServerContext):
    async def on_ls(self, tokens: Dict[str, str]):
        await self._sts(tokens)

        caps = list(self.server.desired_caps)+CAPS

        if (not self.server.params.sasl is None and
                not CAP_SASL in caps):
            caps.append(CAP_SASL)

        matched   = (c.available(tokens) for c in caps)
        cap_names = [name for name in matched if not name is None]

        if cap_names:
            await self.server.send(build("CAP", ["REQ", " ".join(cap_names)]))

            while cap_names:
                line = await self.server.wait_for(ResponseOr(
                    Response("CAP", [ParamAny(), "ACK"]),
                    Response("CAP", [ParamAny(), "NAK"])
                ))

                current_caps = line.params[2].split(" ")
                for cap in current_caps:
                    if cap in cap_names:
                        cap_names.remove(cap)
        if (self.server.cap_agreed(CAP_SASL) and
                not self.server.params.sasl is None):
            await self.server.sasl_auth(self.server.params.sasl)

    async def handshake(self):
        await self.on_ls(self.server.available_caps)
        await self.server.send(build("CAP", ["END"]))

    async def _sts(self, tokens: Dict[str, str]):
        cap_sts = CAP_STS.available(tokens)
        if not cap_sts is None:
            sts_dict = _cap_dict(tokens[cap_sts])
            params   = self.server.params
            if not params.tls:
                if "port" in sts_dict:
                    params.port = int(sts_dict["port"])
                    params.tls  = True

                    await self.server.bot.disconnect(self.server)
                    await self.server.bot.add_server(self.server.name, params)
                    raise ServerDisconnectedException()

            elif "duration" in sts_dict:
                policy = STSPolicy(
                    int(time()),
                    params.port,
                    int(sts_dict["duration"]),
                    "preload" in sts_dict)
                await self.server.sts_policy(policy)

