import json
import os
import asyncio
import shutil
from .configs import default_test_config as config

from .client import Client
from .match.matches import MatchSourceType
from .utl import Utl
from rust_ac import Server
from pathlib import Path

# Sanity check the config and remind people to check their config
assert config.TEST_MODE, "LOCAL_TEST_MODE config value must must be set to True to run tests." + os.linesep \
                         + "IMPORTANT: Are you configured properly for tests?"
assert config.MATCH_SOURCE_CONFIG.TYPE == MatchSourceType.FILE, "MatchSourceType must be set to FILE to run tests." \
                                                                + os.linesep \
                         + "IMPORTANT: Are you configured properly for tests?"

utl = Utl(config)

iterations = 1
games = {
    'loser_bot,T,python,loser_bot,T,python,AutomatonLE': "Tie",
    'basic_bot,T,python,crash,T,python,AutomatonLE': "Player2Crash",
    'basic_bot,T,python,connect_timeout,T,python,AutomatonLE': "InitializationError",
    'basic_bot,T,python,crash_on_first_frame,T,python,AutomatonLE': "Player2Crash",
    'basic_bot,T,python,hang,T,python,AutomatonLE': "Player2Crash",
    'basic_bot,T,python,instant_crash,T,python,AutomatonLE': "InitializationError",
    'crash,T,python,basic_bot,T,python,AutomatonLE': "Player1Crash",
    'connect_timeout,T,python,basic_bot,T,python,AutomatonLE': "InitializationError",
    'crash_on_first_frame,T,python,basic_bot,T,python,AutomatonLE': "Player1Crash",
    'hang,T,python,basic_bot,T,python,AutomatonLE': "Player1Crash",
    'instant_crash,T,python,basic_bot,T,python,AutomatonLE': "InitializationError",
    'loser_bot,T,python,basic_bot,T,python,AutomatonLE': "Player2Win",
    'basic_bot,T,python,loser_bot,T,python,AutomatonLE': "Player1Win",
    'timeout_bot,T,python,timeout_bot,T,python,AutomatonLE': "Tie",
}

ORIGINAL_MAX_GAME_TIME = config.MAX_GAME_TIME


def setup_bots():
    bots_path = Path("../aiarena-test-bots")
    to_bots_path = Path("bots/")

    if not bots_path.exists():
        raise NotADirectoryError(f"{bots_path} does not exist")
    elif len([x for x in bots_path.iterdir() if x.is_dir()]) == 0:
        raise FileNotFoundError(f"{bots_path} is empty. Did you do git clone --recursive?")
    else:
        if not to_bots_path.exists():
            shutil.copytree(bots_path, to_bots_path)


def cleanup():
    bots_path = Path("bots/")
    if bots_path.exists():
        bots_path.rmdir()


async def run_tests():
    """
    Run tests.
    """
    with open('test_results.txt', 'w+') as f:  # Clear results file
        f.write('')

    for it in range(iterations):
        for key, value in games.items():

            with open(config.MATCH_SOURCE_CONFIG.MATCHES_FILE, "w+") as f:
                f.write(key + os.linesep)
            if key == 'loser_bot,T,python,loser_bot,T,python,AutomatonLE':
                config.MAX_GAME_TIME = 1000
            else:
                config.MAX_GAME_TIME = ORIGINAL_MAX_GAME_TIME

            ac = Client(config)
            await ac.run()

            try:
                with open(config.MATCH_SOURCE_CONFIG.RESULTS_FILE, "r") as f:
                    result = json.load(f)
                test_result = f"Result ({str(result['Results'][0]['Result'])}) matches expected result ({value}):" + \
                              str(result["Results"][0]["Result"] == value)
                utl.printout(test_result)
                assert(str(result['Results'][0]['Result']) == value)
                with open('test_results.txt', 'a+') as f:
                    f.write(str(key) + '\t' + str(test_result) + '\n')
            except FileNotFoundError:
                utl.printout("Test failed: Results file not found")
            except KeyError:
                utl.printout("Test failed: Result not found in file")


if __name__ == "__main__":
    s = Server('127.0.0.1:8642')
    s.run()
    setup_bots()
    
    asyncio.get_event_loop().run_until_complete(run_tests())
    s.kill()
    cleanup()
