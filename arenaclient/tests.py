import json
import os
import asyncio
import shutil
import logging
from arenaclient.configs import default_test_config as config

from arenaclient.client import Client
from arenaclient.match.matches import MatchSourceType
from arenaclient.utl import Utl
from pathlib import Path

logging.getLogger().setLevel(config.LOGGING_LEVEL)  # Logging needs to be initialized before importing rust_ac
logging.info("")
from rust_ac import Server


def test_assertions():
    assert config.TEST_MODE, "LOCAL_TEST_MODE config value must must be set to True to run tests." + os.linesep \
                             + "IMPORTANT: Are you configured properly for tests?"
    assert config.MATCH_SOURCE_CONFIG.TYPE == MatchSourceType.FILE, "MatchSourceType must be set to FILE to run " \
                                                                    "tests." \
                                                                    + os.linesep \
                                                                    + "IMPORTANT: Are you configured properly for " \
                                                                      "tests? "


class IntegrationTest:
    def __init__(self, matches_json, iterations=1):
        self.matches = matches_json
        self.utl = Utl(config)
        self.iterations = iterations
        self.original_max_time = config.MAX_GAME_TIME

    async def run_tests(self):
        """
        Run tests.
        """
        # Sanity check the config and remind people to check their config
        test_assertions()
        with open('test_results.txt', 'w+') as f:  # Clear results file
            f.write('')

        for it in range(self.iterations):
            for key, value in self.matches.items():

                with open(config.MATCH_SOURCE_CONFIG.MATCHES_FILE, "w+") as f:
                    f.write(key + os.linesep)
                if key == 'loser_bot,T,python,loser_bot,T,python,AutomatonLE':
                    config.MAX_GAME_TIME = 1000
                else:
                    config.MAX_GAME_TIME = self.original_max_time

                self._purge_previous_results()

                ac = Client(config)
                await ac.run()

                try:
                    with open(config.MATCH_SOURCE_CONFIG.RESULTS_FILE, "r") as f:
                        result = json.load(f)
                    test_result = f"Result ({str(result['Results'][0]['Result'])}) " \
                                  f"matches expected result ({value}):" + \
                                  str(result["Results"][0]["Result"] == value)
                    self.utl.printout(test_result)
                    assert (str(result['Results'][0]['Result']) == value)
                    with open('test_results.txt', 'a+') as f:
                        f.write(str(key) + '\t' + str(test_result) + '\n')
                except FileNotFoundError:
                    self.utl.printout("Test failed: Results file not found")
                except KeyError:
                    self.utl.printout("Test failed: Result not found in file")

    @staticmethod
    def _purge_previous_results():
        try:
            os.remove(config.MATCH_SOURCE_CONFIG.RESULTS_FILE)
        except OSError:
            pass


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


if __name__ == "__main__":
    s = Server('127.0.0.1:8642')
    s.run()
    # setup_bots()

    asyncio.get_event_loop().run_until_complete(run_tests())
    s.kill()
    # cleanup()
