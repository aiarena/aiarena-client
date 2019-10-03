#########################################################
#                                                       #
# DEFAULT CONFIG                                        #
#                                                       #
# !!!! DO NOT UPDATE THIS FILE WITH LOCAL SETTINGS !!!! #
# Create a config.py file to override config values     #
#                                                       #
#########################################################
import logging
import os
import platform
from urllib import parse

# GERERAL
ARENA_CLIENT_ID = "aiarenaclient_000"
API_TOKEN = "12345"
ROUNDS_PER_RUN = 5
SHUT_DOWN_AFTER_RUN = True
RUN_REPLAY_CHECK = True
USE_PID_CHECK = False
DEBUG_MODE = True
PYTHON = "python3"
RUN_LOCAL = False
SYSTEM = platform.system()
SC2_PROXY = {"HOST": "127.0.0.1", "PORT": 8765}


# LOGGING
LOGGING_HANDLER = logging.FileHandler("supervisor.log", "a+")
LOGGING_LEVEL = 10

# PATHS AND FILES
TEMP_PATH = "/tmp/aiarena/"
LOCAL_PATH = os.path.dirname(__file__)
WORKING_DIRECTORY = LOCAL_PATH  # same for now
LOG_FILE = os.path.join(WORKING_DIRECTORY, "aiarena-client.log")
REPLAYS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "replays")

# WEBSITE
BASE_WEBSITE_URL = "https://ai-arena.net"
API_MATCHES_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/matches/")
API_RESULTS_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/results/")

# STARCRAFT
SC2_HOME = "/home/aiarena/StarCraftII/"
SC2_BINARY = os.path.join(SC2_HOME, "Versions/Base75689/SC2_x64")

# todo: download relevant settings from the API
SC2LADDERSERVER_CONFIG_JSON = (
    "{"
    '    "LocalReplayDirectory": "./replays/",'
    '    "MaxGameTime": 60480,'
    '    "MatchupGenerator": "File",'
    '    "MatchupListFile": "./matchuplist",'
    '    "ErrorListFile": "./errorlist",'
    '    "BotConfigFile": "./LadderBots.json",'
    '    "EnableReplayUpload": "False",'
    '    "ResultsLogFile": "./results.json",'
    '    "PlayerIdFile": "./playerids",'
    '    "PythonBinary": "/home/aiarena/venv/bin/python",'
    '    "RealTimeMode": false,'
    '    "Maps": [],'
    '    "MaxFrameTime": 20000'
    "}"
)
MAX_GAME_TIME = 60486
MAX_FRAME_TIME = 1000
STRIKES = 10

CLEANUP_FILES_BETWEEN_ROUNDS = True
FILES_TO_CLEANUP = [
    SC2LADDERSERVER_PID_FILE,
    SC2LADDERSERVER_MATCHUP_LIST_FILE,
    SC2LADDERSERVER_LADDERBOTS_FILE,
    SC2LADDERSERVER_PLAYERIDS_FILE,
    SC2LADDERSERVER_RESULTS_FILE,
    SC2LADDERSERVER_STDOUT_FILE,
    SC2LADDERSERVER_STDERR_FILE,
]

# Override values with environment specific config
try:
    from config import *
except ImportError as e:
    if e.name == "config":
        pass
    else:
        raise
