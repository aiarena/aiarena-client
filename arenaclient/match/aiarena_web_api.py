import json
from urllib import parse

import requests

from ..utl import Utl


class AiArenaWebACApi:
    """
    An interface to the AI Arena website ArenaClient API
    """
    API_MATCHES_ENDPOINT = "/api/arenaclient/matches/"
    API_RESULTS_ENDPOINT = "/api/arenaclient/results/"

    def __init__(self, api_url, api_token, global_config):
        self.API_URL = api_url
        self.API_TOKEN = api_token

        self.API_MATCHES_URL = parse.urljoin(self.API_URL, AiArenaWebACApi.API_MATCHES_ENDPOINT)
        self.API_RESULTS_URL = parse.urljoin(self.API_URL, AiArenaWebACApi.API_RESULTS_ENDPOINT)

        self._utl = Utl(global_config)

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



