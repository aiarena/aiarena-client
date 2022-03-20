import json
import os
import time
from urllib import parse

import requests

from ..utl import Utl


class AiArenaWebApi:
    """
    Handles communication with the AI Arena website arenaclient API.
    """
    API_MATCHES_ENDPOINT = "/api/arenaclient/matches/"
    API_RESULTS_ENDPOINT = "/api/arenaclient/results/"

    def __init__(self, api_url, api_token, global_config):
        self.API_URL = api_url
        self.API_TOKEN = api_token

        self.API_MATCHES_URL = parse.urljoin(self.API_URL, AiArenaWebApi.API_MATCHES_ENDPOINT)
        self.API_RESULTS_URL = parse.urljoin(self.API_URL, AiArenaWebApi.API_RESULTS_ENDPOINT)

        self.debug_mode = global_config.DEBUG_MODE

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

    def submit_result(self,
                      match_id,
                      result,
                      replay_file_path,
                      bot1_data_path,
                      bot2_data_path,
                      bot1_error_log_zip_path,
                      bot2_error_log_zip_path,
                      arenaclient_log_zip):
        attempt_number = 1
        while attempt_number < 60:
            try:  # Upload replay file and bot data archives
                self._utl.printout(
                    f"Attempting to submit result. Attempt number: {attempt_number}."
                )
                file_list = {
                    "bot1_data": open(bot1_data_path, "rb"),
                    "bot2_data": open(bot2_data_path, "rb"),
                    "bot1_log": open(bot1_error_log_zip_path, "rb"),
                    "bot2_log": open(bot2_error_log_zip_path, "rb"),
                    "arenaclient_log": open(arenaclient_log_zip, "rb"),
                }

                if os.path.isfile(replay_file_path):
                    file_list["replay_file"] = open(replay_file_path, "rb")

                payload = {"type": result.result, "match": int(match_id), "game_steps": result.game_time}

                if result.bot1_avg_frame is not None:
                    payload["bot1_avg_step_time"] = result.bot1_avg_frame
                if result.bot2_avg_frame is not None:
                    payload["bot2_avg_step_time"] = result.bot2_avg_frame

                if result.bot1_tags is not None:
                    payload["bot1_tags"] = result.bot1_tags

                if result.bot2_tags is not None:
                    payload["bot2_tags"] = result.bot2_tags

                if self.debug_mode:
                    self._utl.printout(json.dumps(payload))

                post = requests.post(
                    self.API_RESULTS_URL,
                    files=file_list,
                    data=payload,
                    headers={"Authorization": "Token " + self.API_TOKEN},
                )
                if post is None:
                    self._utl.printout("ERROR: Result submission failed. 'post' was None.")
                    attempt_number += 1
                    time.sleep(60)
                elif post.status_code >= 400:  # todo: retry?
                    self._utl.printout(
                        f"ERROR: Result submission failed. Status code: {post.status_code}."
                    )
                    attempt_number += 1
                    time.sleep(60)
                else:
                    self._utl.printout(result.result + " - Result transferred")
                    break
            except ConnectionError:
                self._utl.printout(f"ERROR: Result submission failed. Connection to website failed.")



