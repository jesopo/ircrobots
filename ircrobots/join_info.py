from typing    import Dict, Iterable, List, Optional
from irctokens import build
from ircstates.numerics import *

from .contexts  import ServerContext
from .matching  import Response, ResponseOr, ParamAny, ParamFolded

"""
class JoinContext(ServerContext):
    async def enlighten(self, channels: List[str]):
        folded  = [self.server.casefold(c) for c in channels]
        waiting = len(folded)
        while waiting:
            line = await self.server.wait_for(ResponseOr(
                Response("JOIN", [ParamAny()])
            ))

            if (line.command == "JOIN" and
                    self.server.casefold(line.params[0]) in folded):
                waiting -= 1

        for channel in folded:
            await self.server.send(build("WHO", [channel]))
            line = await self.wait_for(
                Response(RPL_ENDOFWHO, [ParamAny(), ParamFolded(channel)])
            )

        return [self.server.channels[c] for c in folded]
"""

class WHOContext(ServerContext):
    async def ensure(self, channel: str):
        folded = self.server.casefold(channel)

        if self.server.isupport.whox:
            await self.server.send(self.server.prepare_whox(channel))
        else:
            await self.server.send(build("WHO", [channel]))

        line = await self.server.wait_for(
            Response(RPL_ENDOFWHO, [ParamAny(), ParamFolded(folded)])
        )
