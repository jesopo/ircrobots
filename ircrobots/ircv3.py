from typing    import Dict, Iterable, List, Optional
from irctokens import build

from .contexts  import ServerContext
from .matching  import Response, ResponseOr, ParamAny, ParamLiteral
from .interface import ICapability

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

        self._caps = set((ratified_name, draft_name))

    def available(self, capabilities: Iterable[str]
            ) -> Optional[str]:
        match = list(set(capabilities)&self._caps)
        return match[0] if match else None

    def match(self, capability: str) -> Optional[str]:
        cap = list(set([capability])&self._caps)
        return cap[0] if cap else None

    def copy(self):
        return Capability(
            self.name,
            self.draft,
            alias=self.alias,
            depends_on=self.depends_on[:])

CAP_SASL  = Capability("sasl")
CAP_ECHO  = Capability("echo-message")
CAP_LABEL = Capability("labeled-response", "draft/labeled-response-0.2")

LABEL_TAG = {
    "draft/labeled-response-0.2": "draft/label",
    "labeled-response": "label"
}

CAPS: List[ICapability] = [
    Capability("multi-prefix"),
    Capability("chghost"),
    Capability("away-notify"),
    Capability("userhost-in-names"),

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

class CAPContext(ServerContext):
    async def on_ls(self, tokens: Dict[str, str]):
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
                    Response("CAP", [ParamAny(), ParamLiteral("ACK")]),
                    Response("CAP", [ParamAny(), ParamLiteral("NAK")])
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
