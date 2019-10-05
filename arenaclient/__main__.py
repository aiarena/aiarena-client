from arenaclient.client import Client
# the default config will also import custom config values
import arenaclient.default_config as cfg

if __name__ == "__main__":  # execute only if run as a script
    ac = Client(cfg)
    ac.run()
