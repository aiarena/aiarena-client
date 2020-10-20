import asyncio
import logging
import os
from .client import Client
# the default config will also import custom config values
from .configs import default_config as cfg

logging.getLogger().setLevel(logging.DEBUG)  # Logging needs to be initialized before importing rust_ac
logging.basicConfig(filename="proxy.log", level=logging.DEBUG, filemode="w+")
logging.info("")
from rust_ac import Server


async def run_client():
    ac = Client(cfg)
    await ac.run()

if __name__ == "__main__":  # execute only if run as a script
    os.environ['SC2_PROXY_BASE'] = cfg.SC2_HOME
    os.environ['SC2_PROXY_BIN'] = "SC2_x64"
    HOST = cfg.SC2_PROXY["HOST"]
    PORT = cfg.SC2_PROXY["PORT"]
    server = Server(f"{HOST}:{PORT}")
    try:
        server.run()
        asyncio.get_event_loop().run_until_complete(run_client())
    except Exception as e:
        print(e)
        server.kill()
