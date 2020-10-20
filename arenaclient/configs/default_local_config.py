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
from ..match.matches import FileMatchSource

# GENERAL
ARENA_CLIENT_ID = "aiarenaclient_000"
API_TOKEN = "12345"
ROUNDS_PER_RUN = 5
SHUT_DOWN_AFTER_RUN = True
USE_PID_CHECK = False
DEBUG_MODE = False
PYTHON = "python3.7"
RUN_LOCAL = True
CLEANUP_BETWEEN_ROUNDS = False
SYSTEM = platform.system()
SC2_PROXY = {"HOST": "127.0.0.1", "PORT": 8765}
SECURE_MODE = False
SECURE_PLAYER1_USERNAME = None
SECURE_PLAYER2_USERNAME = None


# LOGGING
LOGGING_HANDLER = logging.FileHandler("../supervisor.log", "a+")
LOGGING_LEVEL = 10

# PATHS AND FILES
TEMP_PATH = "/tmp/aiarena/"
LOCAL_PATH = os.path.dirname(__file__)
WORKING_DIRECTORY = LOCAL_PATH  # same for now
LOG_FILE = os.path.join(WORKING_DIRECTORY, "client.log")
REPLAYS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "replays")
BOT_LOGS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "logs")
BOTS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "bots")
VISUALIZE = False

MATCH_SOURCE_CONFIG = FileMatchSource.FileMatchSourceConfig(		
    matches_file=os.path.join(WORKING_DIRECTORY, "matches"),		
    results_file=os.path.join(WORKING_DIRECTORY, "results")		
)

# WEBSITE
BASE_WEBSITE_URL = "https://ai-arena.net"
API_MATCHES_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/matches/")
API_RESULTS_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/results/")

# STARCRAFT
SC2_HOME = "/home/aiarena/StarCraftII/"
SC2_BINARY = os.path.join(SC2_HOME, "Versions/Base75689/SC2_x64")
MAX_GAME_TIME = 60486
MAX_REAL_TIME = 7200  # 2 hours in seconds
MAX_FRAME_TIME = 1000
STRIKES = 10
REALTIME = False

# MATCHES
DISABLE_DEBUG = True
VALIDATE_RACE = False

# Override values with environment specific config
try:
    from local_config import *
except ImportError as e:
    if e.name == "local_config":
        pass
    else:
        raise
