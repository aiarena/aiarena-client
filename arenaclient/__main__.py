import argparse
import asyncio
import logging
import os
from .client import Client
# the default config will also import custom config values
from .configs import default_config as cfg

logging.getLogger().setLevel(cfg.LOGGING_LEVEL)  # Logging needs to be initialized before importing rust_ac
logging.basicConfig(filename="proxy.log",
                    level=cfg.LOGGING_LEVEL,
                    filemode="w+",
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',)
logging.info("")
from rust_ac import Server


async def run_client():
    ac = Client(cfg)
    await ac.run()

if __name__ == "__main__":  # execute only if run as a script
    parser = argparse.ArgumentParser()
    parser.add_argument("--test",  help='Run tests', required=False, action="store_true")
    args, unknown = parser.parse_known_args()

    if args.test:
        import json
        from .tests import IntegrationTest
        with open("./testing/test_matches_aiarena_client_bots.json") as f:
            matches = json.load(f)
            server = Server('127.0.0.1:8642')
            integration_test = IntegrationTest(matches)
            try:
                server.run()
                asyncio.get_event_loop().run_until_complete(integration_test.run_tests())
            except Exception as e:
                print(e)
                server.kill()
                raise e

    else:
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
