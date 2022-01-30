import asyncio

from irctokens import Line, build

from ircrobots import Bot as BaseBot
from ircrobots import ConnectionParams
from ircrobots import Server as BaseServer

SERVERS = [("freenode", "chat.freenode.invalid")]


class Server(BaseServer):
    async def line_read(self, line: Line):
        print(f"{self.name} < {line.format()}")
        if line.command == "001":
            print(f"connected to {self.isupport.network}")
            await self.send(build("JOIN", ["#testchannel"]))

    async def line_send(self, line: Line):
        print(f"{self.name} > {line.format()}")


class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)


async def main():
    bot = Bot()
    for name, host in SERVERS:
        params = ConnectionParams("BitBotNewTest", host, 6697)
        await bot.add_server(name, params)

    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
