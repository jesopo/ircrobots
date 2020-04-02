from typing import Iterable, List, Optional

class Capability(object):
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

CAP_SASL = Capability("sasl")
CAPS = [
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
