import asyncio

from irctokens import build, Line
from ircrobots import Bot as BaseBot
from ircrobots import Server as BaseServer
from ircrobots import ConnectionParams, SASLUserPass, SASLSCRAM

class Server(BaseServer):
    async def line_read(self, line: Line):
        print(f"{self.name} < {line.format()}")
    async def line_send(self, line: Line):
        print(f"{self.name} > {line.format()}")

class Bot(BaseBot):
    def create_server(self, name: str):
        return Server(self, name)

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
