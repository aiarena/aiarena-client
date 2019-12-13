##########################################################
#                                                        #
# DEFAULT TEST CONFIG                                    #
#                                                        #
# !!!! DO NOT UPDATE THIS FILE WITH LOCAL SETTINGS !!!!  #
# Create a test_config.py file to override config values #
#                                                        #
##########################################################
import logging
import os
import platform
from urllib import parse

from arenaclient.matches import FileMatchSource

# GERERAL
ARENA_CLIENT_ID = "aiarenaclient_test"
API_TOKEN = ""
ROUNDS_PER_RUN = 1
SHUT_DOWN_AFTER_RUN = True
USE_PID_CHECK = False
DEBUG_MODE = True
PYTHON = "python"
TEST_MODE = True
CLEANUP_BETWEEN_ROUNDS = False
SYSTEM = platform.system()
SC2_PROXY = {"HOST": "127.0.0.1", "PORT": 8765}
RUN_LOCAL = True
# LOGGING
LOGGING_HANDLER = logging.FileHandler("supervisor.log", "a+")
LOGGING_LEVEL = 10

# PATHS AND FILES
TEMP_PATH = "/tmp/aiarena/"
LOCAL_PATH = os.path.dirname(__file__)
WORKING_DIRECTORY = LOCAL_PATH  # same for now
LOG_FILE = os.path.join(WORKING_DIRECTORY, "client.log")
REPLAYS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "replays")
BOTS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "bots")
BOT_LOGS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "logs")

MATCH_SOURCE_CONFIG = FileMatchSource.FileMatchSourceConfig(
    matches_file=os.path.join(WORKING_DIRECTORY, "matches"),
    results_file=os.path.join(WORKING_DIRECTORY, "results")
)

# WEBSITE
BASE_WEBSITE_URL = "https://ai-arena.net"
API_MATCHES_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/matches/")
API_RESULTS_URL = parse.urljoin(BASE_WEBSITE_URL, "/api/arenaclient/results/")

# STARCRAFT
MAX_GAME_TIME = 60486
MAX_FRAME_TIME = 1000
STRIKES = 10
REALTIME = False
VISUALIZE = False
# Override values with environment specific config
try:
    from arenaclient.test_config import *
except ImportError as e:
    if e.name == "arenaclient.test_config":
        pass
    else:
        raise
