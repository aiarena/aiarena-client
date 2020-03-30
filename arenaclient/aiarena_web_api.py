import json
from urllib import parse

import requests

from arenaclient.utl import Utl


class AiArenaWebApi:
    """
    Match class to handle the Ai-Arena API
    """
    API_MATCHES_ENDPOINT = "/api/arenaclient/matches/"
    API_RESULTS_ENDPOINT = "/api/arenaclient/results/"

    def __init__(self, api_url, api_token, global_config):
        self.API_URL = api_url
        self.API_TOKEN = api_token

        self.API_MATCHES_URL = parse.urljoin(self.API_URL, AiArenaWebApi.API_MATCHES_ENDPOINT)
        self.API_RESULTS_URL = parse.urljoin(self.API_URL, AiArenaWebApi.API_RESULTS_ENDPOINT)

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

    def submit_result(self):
        """
        Overridden in matches.py

        """
        pass



