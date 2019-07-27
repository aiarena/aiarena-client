# EXAMPLE CONFIG - COPY THIS TO config.py

import os
from urllib import parse

# GERERAL
ARENA_CLIENT_ID = "aiarenaclient_000"
API_TOKEN = "???"
ROUNDS_PER_RUN = 5
SHUT_DOWN_AFTER_RUN = True
RUN_REPLAY_CHECK = True

# PATHS AND FILES
TEMP_PATH = "/tmp/aiarena/"
LOCAL_PATH = os.path.dirname(__file__)
WORKING_DIRECTORY = LOCAL_PATH  # same for now
LOG_FILE = os.path.join(WORKING_DIRECTORY, "aiarena-client.log")
REPLAYS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "replays")
RESULT_CHECK_JSON_FILE = os.path.join(LOCAL_PATH, "results.json")

# WEBSITE
BASE_WEBSITE_URL = "https://ai-arena.net"
API_MATCHES_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/matches/")
API_RESULTS_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/results/")

# STARCRAFT
SC2_HOME = "/home/aiarena/StarCraftII/"
SC2_BINARY = os.path.join(SC2_HOME, "Versions/Base70154/SC2_x64")

# SC2LADDERSERVER
SC2LADDERSERVER_STDOUT_FILE = os.path.join(LOCAL_PATH, "sc2ladderserver_stdout.log")
SC2LADDERSERVER_STDERR_FILE = os.path.join(LOCAL_PATH, "sc2ladderserver_stderr.log")
SC2LADDERSERVER_BINARY = os.path.join(LOCAL_PATH, "Sc2LadderServer")
SC2LADDERSERVER_MATCHUP_LIST_FILE = os.path.join(LOCAL_PATH, "matchuplist")
SC2LADDERSERVER_LADDERBOTS_FILE = os.path.join(LOCAL_PATH, "LadderBots.json")
SC2LADDERSERVER_PLAYERIDS_FILE = os.path.join(LOCAL_PATH, "playerids")
SC2LADDERSERVER_RESULTS_FILE = os.path.join(LOCAL_PATH, "results.json")