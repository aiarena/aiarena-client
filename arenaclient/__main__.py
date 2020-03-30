from arenaclient.client import Client
# the default config will also import custom config values
import arenaclient.default_config as cfg
import asyncio
from multiprocessing import Process
from argparse import ArgumentParser
from arenaclient.proxy.server import run_server

async def run_client():
    ac = Client(cfg)
    await ac.run()

if __name__ == "__main__":  # execute only if run as a script
    parser = ArgumentParser()

    parser.add_argument("-f","--frontend", help="Start server with frontend", action="store_true")

    args, unknown = parser.parse_known_args()
    run_frontend = args.frontend

    if 'false' in [x.lower() for x in unknown]:
        run_frontend = False
        
    if run_frontend:
        proc = Process(target=run_server, args=(True,))
        proc.daemon = True
        proc.start()
        proc.join()
    else:
        asyncio.get_event_loop().run_until_complete(run_client())
