from time        import time
from typing      import Dict, Iterable, List, Optional, Tuple
from dataclasses import dataclass
from irctokens   import build
from ircstates.server import ServerDisconnectedException

from .contexts  import ServerContext
from .matching  import Response, ANY
from .interface import ICapability
from .params    import ConnectionParams, STSPolicy, ResumePolicy

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

class MessageTag(object):
    def __init__(self,
            name: Optional[str],
            draft_name: Optional[str]=None):
        self.name  = name
        self.draft = draft_name
        self._tags = [self.name, self.draft]

    def available(self, tags: Iterable[str]) -> Optional[str]:
        for tag in self._tags:
            if tag is not None and tag in tags:
                return tag
        else:
            return None

    def get(self, tags: Dict[str, str]) -> Optional[str]:
        name = self.available(tags)
        if name is not None:
            return tags[name]
        else:
            return None

CAP_SASL   = Capability("sasl")
CAP_ECHO   = Capability("echo-message")
CAP_STS    = Capability("sts", "draft/sts")
CAP_RESUME = Capability(None, "draft/resume-0.5", alias="resume")

CAP_LABEL  = Capability("labeled-response", "draft/labeled-response-0.2")
TAG_LABEL  = MessageTag("label", "draft/label")
LABEL_TAG_MAP = {
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
    Capability("setname", "draft/setname"),
    CAP_RESUME
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
async def resume_transmute(params: ConnectionParams):
    if params.resume is not None:
        params.host = params.resume.address

class HandshakeCancel(Exception):
    pass

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
                line = await self.server.wait_for({
                    Response("CAP", [ANY, "ACK"]),
                    Response("CAP", [ANY, "NAK"])
                })

                current_caps = line.params[2].split(" ")
                for cap in current_caps:
                    if cap in cap_names:
                        cap_names.remove(cap)
                if CAP_RESUME.available(current_caps):
                    await self.resume_token()

        if (self.server.cap_agreed(CAP_SASL) and
                not self.server.params.sasl is None):
            await self.server.sasl_auth(self.server.params.sasl)

    async def resume_token(self):
        line = await self.server.wait_for(Response("RESUME", ["TOKEN", ANY]))
        token = line.params[1]
        address, port = self.server.server_address()
        resume_policy = ResumePolicy(address, token)

        previous_policy = self.server.params.resume
        self.server.params.resume = resume_policy
        await self.server.resume_policy(resume_policy)

        if previous_policy is not None and not self.server.registered:
            await self.server.send(build("RESUME", [previous_policy.token]))
            line = await self.server.wait_for({
                Response("RESUME", ["SUCCESS"]),
                Response("FAIL",   ["RESUME"])
            })
            if line.command == "RESUME":
                raise HandshakeCancel()

    async def handshake(self):
        try:
            await self.on_ls(self.server.available_caps)
        except HandshakeCancel:
            return
        else:
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

