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

# GENERAL
from ..match.matches import FileMatchSource

ARENA_CLIENT_ID = "aiarenaclient_000"  # ID of arenaclient. Used for AiArena
API_TOKEN = "12345"  # API Token to retrieve matches and submit results. Used for AiArena
ROUNDS_PER_RUN = 5  # Set to -1 to ignore this
BASE_WEBSITE_URL = ""
USE_PID_CHECK = False
RUN_REPLAY_CHECK = False  # Validate replays
DEBUG_MODE = True  # Enables debug mode for more logging
PYTHON = "python3"  # Which python version to use
RUN_LOCAL = False  # Run on AiArena or locally
CLEANUP_BETWEEN_ROUNDS = True  # Clean up files between rounds
SYSTEM = platform.system()  # What OS are we on?
SC2_PROXY = {"HOST": "127.0.0.1", "PORT": 8765}  # On which host and port to run the proxy between SC2 and bots

# Secure mode will ignore the BOTS_DIRECTORY config setting and instead run each bot in their home directory.
SECURE_MODE = False
# Specify the users (if any) to run the bots as.
RUN_PLAYER1_AS_USER = None
RUN_PLAYER2_AS_USER = None

# LOGGING
LOGGING_HANDLER = logging.FileHandler("../supervisor.log", "a+")
LOGGING_LEVEL = 10

# PATHS AND FILES
TEMP_ROOT = "/tmp/"
TEMP_PATH = os.path.join(TEMP_ROOT, "aiarena")
LOCAL_PATH = os.path.dirname(__file__)
WORKING_DIRECTORY = LOCAL_PATH  # same for now
LOG_FILE = os.path.join(WORKING_DIRECTORY, "client.log")
REPLAYS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "replays")
BOTS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "bots")  # Ignored when SECURE_MODE == True
CLEAN_BOT_DIRECTORIES_BEFORE_MATCH_START = True  # a quick fix to stop attempting to clean a non-existent bot directory

MATCH_SOURCE_CONFIG = FileMatchSource.FileMatchSourceConfig(
    matches_file=os.path.join(WORKING_DIRECTORY, "matches"),
    results_file=os.path.join(WORKING_DIRECTORY, "results")
)

# STARCRAFT
SC2_HOME = "/home/aiarena/StarCraftII/"
SC2_BINARY = os.path.join(SC2_HOME, "Versions/Base75689/SC2_x64")
MAX_GAME_TIME = 60486
MAX_REAL_TIME = 7200  # 2 hours in seconds
MAX_FRAME_TIME = 1000
STRIKES = 10
REALTIME = False
VISUALIZE = False

# MATCHES
DISABLE_DEBUG = True
VALIDATE_RACE = False
# Override values with environment specific config
try:
    from config import *
except ImportError as e:
    if e.name == "config":
        pass
    else:
        raise
