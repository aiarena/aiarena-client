from arenaclient.arena_client import ArenaClient
from arenaclient import default_config as config

if __name__ == "__main__":  # execute only if run as a script
    ac = ArenaClient(config)
    ac.run()
