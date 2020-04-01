import asyncio

from irctokens import build, Line

from ircrobots.bot    import Bot as BaseBot
from ircrobots.server import ConnectionParams, Server

SERVERS = [
    ("freenode", "chat.freenode.net"),
    ("tilde",    "ctrl-c.tilde.chat")
]

class Bot(BaseBot):
    async def line_read(self, server: Server, line: Line):
        print(f"{server.name}< {line.format()}")
        if line.command == "001":
            print(f"connected to {server.isupport.network}")
            await server.send(build("JOIN", ["#testchannel"]))

    async def line_send(self, server: Server, line: Line):
        print(f"{server.name}> {line.format()}")

async def main():
    bot = Bot()
    for name, host in SERVERS:
        params = ConnectionParams("BitBotNewTest", host, 6697, True)
        await bot.add_server(name, params)
    await bot.run()
if __name__ == "__main__":
    asyncio.run(main())
