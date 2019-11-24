from arenaclient.client import Client
# the default config will also import custom config values
import arenaclient.default_config as cfg
import asyncio

async def run_client():
    ac = Client(cfg)
    await ac.run()

if __name__ == "__main__":  # execute only if run as a script
    asyncio.get_event_loop().run_until_complete(run_client())
    
