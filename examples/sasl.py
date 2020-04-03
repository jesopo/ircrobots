import asyncio

from irctokens import build, Line
from ircrobots import Bot as BaseBot
from ircrobots import ConnectionParams, SASLUserPass, Server

class Bot(BaseBot):
    async def line_read(self, server: Server, line: Line):
        print(f"{server.name} < {line.format()}")

    async def line_send(self, server: Server, line: Line):
        print(f"{server.name} > {line.format()}")

async def main():
    bot = Bot()

    sasl_params = SASLUserPass("myusername", "invalidpassword")
    params      = ConnectionParams(
        "MyNickname",
        host = "chat.freenode.invalid",
        port = 6697,
        tls  = True,
        sasl = sasl_params)

    await bot.add_server("freenode", params)
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())
