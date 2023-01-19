import asyncio

from rust_ac import Server

from arenaclient.client import Client
from arenaclient.configs import default_test_config as config
from arenaclient.match.aiarena_web_api import MockAiArenaWebACApi
from arenaclient.match.matches import HttpApiMatchSource


class ExampleTestMockAiArenaWebACApi(MockAiArenaWebACApi):
    def get_match(self):
        """
        Return a match to test here.
        Remember the bot_zip_url and bot_data_url given for each bot here,
        so download_bot_zip and download_bot_data provide the correct files.
        """

    def submit_result(self, result_type: str, match_id: int, game_steps: str, bot1_data_file_stream,
                      bot2_data_file_stream, bot1_log_file_stream, bot2_log_file_stream,
                      arenaclient_log_zip_file_stream, replay_file_stream=None):
        """Validate match result/expected bot data contents/etc, or cache them so they can be validated by other code"""

    def download_map(self, map_url: str, to_path: str):
        """Save the test map to the to_path"""

    def download_bot_zip(self, bot_zip_url: str, to_path: str):
        """Save the bot zip to the to_path"""

    def download_bot_data(self, bot_data_url: str, to_path: str):
        """Save the bot data to the to_path"""


async def run_test():
    # Replace the match source config with one specificly for this test
    config.MATCH_SOURCE_CONFIG = HttpApiMatchSource.HttpApiMatchSourceConfig(
        api_url=config.BASE_WEBSITE_URL,
        api_token=config.API_TOKEN,
        ac_api_class='arenaclient.mock_aiarena_ac_api_example.ExampleTestMockAiArenaWebACApi'
    )

    ac = Client(config)
    await ac.run()

    # validate test result here or inside ExampleTestMockAiArenaWebACApi.submit_result


if __name__ == "__main__":
    s = Server('127.0.0.1:8642')
    s.run()

    asyncio.get_event_loop().run_until_complete(run_test())
    s.kill()
