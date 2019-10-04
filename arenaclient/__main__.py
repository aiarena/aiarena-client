from arenaclient.client import Client

if __name__ == "__main__":  # execute only if run as a script
    import arenaclient.defaultconfig as cfg  # the default config will also import custom config values
    ac = Client(cfg)
    ac.run()
