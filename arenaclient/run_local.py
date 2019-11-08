import json
import os

import arenaclient.default_local_config as config

from arenaclient.client import Client
from arenaclient.utl import Utl

# Sanity check the config and remind people to check their config
utl = Utl(config)


games = ['loser_bot,T,python,loser_bot,T,python,AutomatonLE']
config.ROUNDS_PER_RUN = 1
games_len = len(games)
config.REALTIME = True
for key in games:    
    with open(config.MATCH_SOURCE_CONFIG.MATCHES_FILE, "w+") as f:
        f.write(key + os.linesep)

    ac = Client(config)
    ac.run()