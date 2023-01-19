import importlib
import json
from abc import ABC, abstractmethod
from urllib import parse

import requests

from ..utl import Utl


class BaseAiArenaWebACApi(ABC):
    """ This is abstracted so that it can be mocked in testing """
    SAFE_FOR_USE_IN_TESTING = False

    def __init__(self, api_url, api_token, global_config):
        self.API_URL = api_url
        self.API_TOKEN = api_token

        if global_config.TEST_MODE:
            assert self.SAFE_FOR_USE_IN_TESTING, \
                "TEST_MODE is set, but this AiArenaWebACApi is not flagged safe for testing!"
        self._utl = Utl(global_config)

    @abstractmethod
    def get_match(self):
        pass

    @abstractmethod
    def submit_result(self, result_type: str, match_id: int, game_steps: str,
                      bot1_data_file_stream, bot2_data_file_stream,
                      bot1_log_file_stream, bot2_log_file_stream,
                      arenaclient_log_zip_file_stream, replay_file_stream=None):
        pass

    @abstractmethod
    def download_map(self, map_url: str, to_path: str):
        pass

    @abstractmethod
    def download_bot_zip(self, bot_zip_url: str, to_path: str):
        pass

    @abstractmethod
    def download_bot_data(self, bot_data_url: str, to_path: str):
        pass


class MockAiArenaWebACApi(BaseAiArenaWebACApi, ABC):
    """
    Inherit this class for testing purposes
    """
    SAFE_FOR_USE_IN_TESTING = True
    pass


class AiArenaWebACApi(BaseAiArenaWebACApi):
    """
    An interface to the live AI Arena website ArenaClient API
    """
    API_MATCHES_ENDPOINT = "/api/arenaclient/matches/"
    API_RESULTS_ENDPOINT = "/api/arenaclient/results/"

    def __init__(self, api_url, api_token, global_config):
        super().__init__(api_url, api_token, global_config)
        self.API_MATCHES_URL = parse.urljoin(self.API_URL, AiArenaWebACApi.API_MATCHES_ENDPOINT)
        self.API_RESULTS_URL = parse.urljoin(self.API_URL, AiArenaWebACApi.API_RESULTS_ENDPOINT)

    def get_match(self):
        """
        Gets the next match in queue
        """
        try:
            next_match_response = requests.post(
                self.API_MATCHES_URL,
                headers={"Authorization": "Token " + self.API_TOKEN},
            )
        except ConnectionError:
            self._utl.printout(
                f"ERROR: Failed to retrieve game. Connection to website failed. Sleeping."
            )
            return None

        if next_match_response.status_code >= 400:
            self._utl.printout(
                f"ERROR: Failed to retrieve game. Status code: {next_match_response.status_code}. Sleeping."
            )
            return None

        return json.loads(next_match_response.text)

    def submit_result(self, result_type: str, match_id: int, game_steps: str,
                      bot1_data_file_stream, bot2_data_file_stream,
                      bot1_log_file_stream, bot2_log_file_stream,
                      arenaclient_log_zip_file_stream, replay_file_stream=None):
        """
        Submits the supplied result to the AI Arena website API
        """

        payload = {"type": result_type, "match": match_id, "game_steps": game_steps}

        file_list = {
            "bot1_data": bot1_data_file_stream,
            "bot2_data": bot2_data_file_stream,
            "bot1_log": bot1_log_file_stream,
            "bot2_log": bot2_log_file_stream,
            "arenaclient_log": arenaclient_log_zip_file_stream,
        }

        if replay_file_stream:
            file_list["replay_file"] = replay_file_stream

        post = requests.post(
            self.API_RESULTS_URL,
            files=file_list,
            data=payload,
            headers={"Authorization": "Token " + self.API_TOKEN},
        )
        return post

    def download_map(self, map_url: str, to_path: str) -> bool:
        success = False
        try:
            r = requests.get(map_url)

            with open(to_path, "wb") as map_file:
                map_file.write(r.content)

            success = True
        except Exception as download_exception:
            self._utl.printout(f"ERROR: Failed to download map at URL {map_url}. Error {download_exception}")

        return success

    def download_bot_zip(self, bot_zip_url: str, to_path: str):
        r = requests.get(
            bot_zip_url, headers={"Authorization": "Token " + self.API_TOKEN}
        )
        with open(to_path, "wb") as bot_zip:
            bot_zip.write(r.content)

    def download_bot_data(self, bot_data_url: str, to_path: str):
        r = requests.get(
            bot_data_url, headers={"Authorization": "Token " + self.API_TOKEN}
        )
        with open(to_path, "wb") as bot_data_zip:
            bot_data_zip.write(r.content)


class AiArenaWebAcApiFactory:
    """
    Builds a AiArenaWebAcApi
    """

    @staticmethod
    def build_api(ac_api_class, api_url, api_token, global_config) -> BaseAiArenaWebACApi:
        ac_api_class_ref = AiArenaWebAcApiFactory._str_to_class_ref(ac_api_class)
        assert issubclass(ac_api_class_ref, BaseAiArenaWebACApi), \
            f"Type {str(ac_api_class_ref)} does not implement BaseAiArenaWebACApi"
        return ac_api_class_ref(api_url, api_token, global_config)

    @staticmethod
    def _str_to_class_ref(ac_api_class):
        """Return a class instance from a string reference"""
        module_name, class_name = ac_api_class.rsplit('.', 1)
        try:
            module_ = importlib.import_module(module_name)
            try:
                class_ = getattr(module_, class_name)
            except AttributeError:
                raise 'Class does not exist'
        except ImportError:
            raise 'Module does not exist'
        return class_ or None
