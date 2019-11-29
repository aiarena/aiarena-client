# This serves as an example of what a config for running local matches might look like.

import os

from arenaclient.matches import FileMatchSource

# GERERAL
ARENA_CLIENT_ID = "aiarenaclient_local"
ROUNDS_PER_RUN = -1
CLEANUP_BETWEEN_ROUNDS = False
PYTHON = "python"

# PATHS AND FILES
LOCAL_PATH = os.path.dirname(__file__)
WORKING_DIRECTORY = LOCAL_PATH  # same for now
LOG_FILE = os.path.join(WORKING_DIRECTORY, "client.log")
REPLAYS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "replays")
BOTS_DIRECTORY = os.path.join(WORKING_DIRECTORY, "bots")
TEMP_PATH = os.path.join(WORKING_DIRECTORY, "tmp")


MATCH_SOURCE_CONFIG = FileMatchSource.FileMatchSourceConfig(
    matches_file=os.path.join(WORKING_DIRECTORY, "matches"),
    results_file=os.path.join(WORKING_DIRECTORY, "results")
)
