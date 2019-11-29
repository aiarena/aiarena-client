import json
import os
import shutil
import time
import zipfile
from enum import Enum
from pathlib import Path
from arenaclient.bot import Bot
from pathlib import Path

import requests

from arenaclient.aiarena_web_api import AiArenaWebApi
from arenaclient.bot import Bot, BotFactory
from arenaclient.utl import Utl


class MatchSourceType(Enum):
    FILE = 1
    HTTP_API = 2


class MatchSource:
    """
    Abstract representation of a source of matches for the arena client to run.
    next_match must be implemented
    submit_result must be implemented
    """

    class MatchSourceConfig:
        def __init__(self, source_type: MatchSourceType):
            self.TYPE: MatchSourceType = source_type

    class Match:
        """
        Abstract representation of a match.
        """

        def __init__(self, match_id, bot1: Bot, bot2: Bot, map_name):
            self.id = match_id

            self.bot1 = bot1
            self.bot2 = bot2

            self.map_name = map_name

    def __init__(self, config: MatchSourceConfig):
        pass

    def has_next(self) -> bool:
        raise NotImplementedError()

    def next_match(self) -> Match:
        raise NotImplementedError()

    def submit_result(self, match: Match, result):
        raise NotImplementedError()


class HttpApiMatchSource(MatchSource):
    """
    Represents a source of matches originating from the AI Arena Website HTTP API
    """

    class HttpApiMatchSourceConfig(MatchSource.MatchSourceConfig):
        def __init__(self, api_url, api_token):
            super().__init__(MatchSourceType.HTTP_API)
            self.API_URL = api_url
            self.API_TOKEN = api_token

    class HttpApiMatch(MatchSource.Match):
        """
        A representation of a match sourced from the AI Arena Website HTTP API.
        """

        def __init__(self, match_id, bot1: Bot, bot2: Bot, map_name):
            super().__init__(match_id, bot1, bot2, map_name)

    def __init__(self, config: HttpApiMatchSourceConfig, global_config):
        super().__init__(config)
        self._api = AiArenaWebApi(config.API_URL, config.API_TOKEN, global_config)
        self._config = global_config
        self._utl = Utl(global_config)

    def has_next(self) -> bool:
        return True  # always return true

    def next_match(self) -> HttpApiMatch:
        next_match_data = self._api.get_match()

        if next_match_data is None:
            time.sleep(30)
            return None  # there was an issue

        if "id" not in next_match_data:
            self._utl.printout("No games available - sleeping")
            time.sleep(30)
            return None

        next_match_id = next_match_data["id"]
        self._utl.printout(f"Next match: {next_match_id}")

        # Download map
        map_name = next_match_data["map"]["name"]
        map_url = next_match_data["map"]["file"]
        self._utl.printout(f"Downloading map {map_name}")

        try:
            r = requests.get(map_url)
        except Exception as download_exception:
            self._utl.printout(f"ERROR: Failed to download map {map_name} at URL {map_url}. Error {download_exception}")
            time.sleep(30)
            return None

        map_path = os.path.join(self._config.SC2_HOME, "maps", f"{map_name}.SC2Map")
        with open(map_path, "wb") as map_file:
            map_file.write(r.content)

        bot_1 = BotFactory.from_api_data(self._config, next_match_data["bot1"])
        if not bot_1.get_bot_file():
            time.sleep(30)
            return None

        bot_2 = BotFactory.from_api_data(self._config, next_match_data["bot2"])
        if not bot_2.get_bot_file():
            time.sleep(30)
            return None

        return HttpApiMatchSource.HttpApiMatch(next_match_id, bot_1, bot_2, map_name)

    def submit_result(self, match: HttpApiMatch, result):
        self._utl.kill_current_server()
        # quick hack to avoid these going uninitialized
        # todo: remove these and actually fix the issue
        game_time: int = 0
        bot1_avg_step_time: float = 0
        bot2_avg_step_time: float = 0

        if isinstance(result, list):
            for x in result:
                if x.get("Result", None):
                    temp_results = x["Result"]
                    self._utl.printout(str(temp_results))
                    bot_1_name = list(x["Result"].keys())[0]
                    bot_2_name = list(x["Result"].keys())[1]

                    if temp_results[bot_1_name] == "Result.Crashed":
                        result_type = "Player1Crash"

                    elif temp_results[bot_2_name] == "Result.Crashed":
                        result_type = "Player2Crash"
                        # result_json['Winner']=bot_0

                    elif temp_results[bot_1_name] == "Result.Timeout":
                        result_type = "Player1TimeOut"

                    elif temp_results[bot_2_name] == "Result.Timeout":
                        result_type = "Player2TimeOut"

                    elif temp_results[bot_1_name] == "Result.Victory":
                        result_type = "Player1Win"
                        # result_json['Winner']=bot_1_name

                    elif temp_results[bot_1_name] == "Result.Defeat":
                        result_type = "Player2Win"
                        # result_json['Winner']=bot_1

                    elif temp_results[bot_2_name] == "Result.Crashed":
                        result_type = "Player2Crash"
                        # result_json['Winner']=bot_0

                    elif temp_results[bot_1_name] == "Result.Tie":
                        result_type = "Tie"
                        # result_json['Winner']='Tie'

                    else:
                        result_type = "InitializationError"
                        game_time = 0
                        bot1_avg_step_time = 0
                        bot2_avg_step_time = 0

                    # result_json['Result'] = result

                if x.get("GameTime", None):
                    game_time = x["GameTime"]

                if x.get("AverageFrameTime", None):
                    try:
                        bot1_avg_step_time = next(
                            item[match.bot1.name] for item in x['AverageFrameTime'] if item.get(match.bot1.name, None))
                    except StopIteration:
                        bot1_avg_step_time = 0
                    try:
                        bot2_avg_step_time = next(
                            item[match.bot2.name] for item in x['AverageFrameTime'] if item.get(match.bot2.name, None))
                    except StopIteration:
                        bot2_avg_step_time = 0

                if x.get("TimeStamp", None):
                    time_stamp = x["TimeStamp"]

        else:
            result_type = result
            game_time = 0
            bot1_avg_step_time = 0
            bot2_avg_step_time = 0

        self._utl.printout(str(result_type))
        replay_file: str = ""
        for file in os.listdir(self._config.REPLAYS_DIRECTORY):
            if file.endswith('.SC2Replay'):
                replay_file = file
                break

        replay_file_path = os.path.join(self._config.REPLAYS_DIRECTORY, replay_file)

        bot1_data_folder = os.path.join(self._config.BOTS_DIRECTORY, match.bot1.name, "data")
        bot2_data_folder = os.path.join(self._config.BOTS_DIRECTORY, match.bot2.name, "data")
        bot1_error_log = os.path.join(bot1_data_folder, "stderr.log")
        bot1_error_log_tmp = os.path.join(self._config.TEMP_PATH, match.bot1.name + "-error.log")
        if os.path.isfile(bot1_error_log):
            shutil.move(bot1_error_log, bot1_error_log_tmp)
        else:
            Path(bot1_error_log_tmp).touch()

        bot2_error_log = os.path.join(bot2_data_folder, "stderr.log")
        bot2_error_log_tmp = os.path.join(self._config.TEMP_PATH, match.bot2.name + "-error.log")
        if os.path.isfile(bot2_error_log):
            shutil.move(bot2_error_log, bot2_error_log_tmp)
        else:
            Path(bot2_error_log_tmp).touch()

        zip_file = zipfile.ZipFile(
            os.path.join(self._config.TEMP_PATH, match.bot1.name + "-error.zip"), "w"
        )
        zip_file.write(
            os.path.join(self._config.TEMP_PATH, match.bot1.name + "-error.log"),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        zip_file.close()

        zip_file = zipfile.ZipFile(
            os.path.join(self._config.TEMP_PATH, match.bot2.name + "-error.zip"), "w"
        )
        zip_file.write(
            os.path.join(self._config.TEMP_PATH, match.bot2.name + "-error.log"),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        zip_file.close()

        # client logs
        proxy_tmp = os.path.join(self._config.TEMP_PATH, "proxy.log")
        # supervisor_tmp = os.path.join(self._config.TEMP_PATH, "supervisor.log")
        client_tmp = os.path.join(self._config.TEMP_PATH, "client.log")

        if os.path.isfile("proxy.log"):
            shutil.move("proxy.log", proxy_tmp)
        else:
            Path(proxy_tmp).touch()

        # if os.path.isfile("supervisor.log"):
        #     shutil.move("supervisor.log", supervisor_tmp)
        # else:
        #     Path(supervisor_tmp).touch()

        if os.path.isfile("client.log"):
            shutil.move("client.log", client_tmp)
        else:
            Path(client_tmp).touch()

        arenaclient_log_zip = os.path.join(self._config.TEMP_PATH, "arenaclient_log.zip")
        zip_file = zipfile.ZipFile(arenaclient_log_zip, "w")
        zip_file.write(proxy_tmp, compress_type=zipfile.ZIP_DEFLATED)
        # zip_file.write(supervisor_tmp, compress_type=zipfile.ZIP_DEFLATED)
        zip_file.write(client_tmp, compress_type=zipfile.ZIP_DEFLATED)
        zip_file.close()

        # Create downloadable data archives
        if not os.path.isdir(bot1_data_folder):
            os.mkdir(bot1_data_folder)
        shutil.make_archive(
            os.path.join(self._config.TEMP_PATH, match.bot1.name + "-data"), "zip", bot1_data_folder
        )
        if not os.path.isdir(bot2_data_folder):
            os.mkdir(bot2_data_folder)
        shutil.make_archive(
            os.path.join(self._config.TEMP_PATH, match.bot2.name + "-data"), "zip", bot2_data_folder
        )

        try:  # Upload replay file and bot data archives
            file_list = {
                "bot1_data": open(
                    os.path.join(self._config.TEMP_PATH, f"{match.bot1.name}-data.zip"), "rb"
                ),
                "bot2_data": open(
                    os.path.join(self._config.TEMP_PATH, f"{match.bot2.name}-data.zip"), "rb"
                ),
                "bot1_log": open(
                    os.path.join(self._config.TEMP_PATH, f"{match.bot1.name}-error.zip"), "rb"
                ),
                "bot2_log": open(
                    os.path.join(self._config.TEMP_PATH, f"{match.bot2.name}-error.zip"), "rb"
                ),
                "arenaclient_log": open(arenaclient_log_zip, "rb"),
            }

            if os.path.isfile(replay_file_path):
                file_list["replay_file"] = open(replay_file_path, "rb")

            payload = {"type": result_type, "match": int(match.id), "game_steps": game_time}

            if bot1_avg_step_time is not None:
                payload["bot1_avg_step_time"] = bot1_avg_step_time
            if bot2_avg_step_time is not None:
                payload["bot2_avg_step_time"] = bot2_avg_step_time

            if self._config.DEBUG_MODE:
                self._utl.printout(json.dumps(payload))

            post = requests.post(
                self._config.API_RESULTS_URL,
                files=file_list,
                data=payload,
                headers={"Authorization": "Token " + self._config.MATCH_SOURCE_CONFIG.API_TOKEN},
            )
            if post is None:
                self._utl.printout("ERROR: Result submission failed. 'post' was None.")
            elif post.status_code >= 400:  # todo: retry?
                self._utl.printout(
                    f"ERROR: Result submission failed. Status code: {post.status_code}."
                )
            else:
                self._utl.printout(result_type + " - Result transferred")
        except ConnectionError:
            self._utl.printout(f"ERROR: Result submission failed. Connection to website failed.")


class FileMatchSource(MatchSource):
    """
    Represents a source of matches originating from a local file

    Expected file format:
    Each match should be on it's own line, line so:
    Bot1Name,Bot1Race,Bot1Type,Bot2Name,Bot2Race[T,P,Z,R],Bot2Type,SC2MapName
    """

    MATCH_FILE_VALUE_SEPARATOR = ','

    class FileMatchSourceConfig(MatchSource.MatchSourceConfig):
        def __init__(self, matches_file, results_file):
            super().__init__(MatchSourceType.FILE)
            self.MATCHES_FILE = matches_file
            self.RESULTS_FILE = results_file
            self.results = []

    class FileMatch(MatchSource.Match):
        """
        A representation of a match sourced from a file.
        """

        def __init__(self, config, match_id, file_line):
            match_values = file_line.split(FileMatchSource.MATCH_FILE_VALUE_SEPARATOR)

            # the last character might be a new line, so rstrip just in case
            map_name = match_values[6].rstrip()
            bot1 = BotFactory.from_values(config, 1, match_values[0], match_values[1], match_values[2])
            bot2 = BotFactory.from_values(config, 2, match_values[3], match_values[4], match_values[5])
            super().__init__(match_id, bot1, bot2, map_name)

    def __init__(self, global_config, config: FileMatchSourceConfig):
        super().__init__(config)
        self._config = global_config
        self._matches_file = config.MATCHES_FILE
        self._results_file = config.RESULTS_FILE

    def has_next(self) -> bool:
        with open(self._matches_file, "r") as match_list:
            for match_id, line in enumerate(match_list):
                if line != '' and line[0] != '#':  # if the line isn't empty or escaped, we've got a match to play
                    return True
        return False

    def next_match(self) -> FileMatch:

        next_match = None

        with open(self._matches_file, "r") as match_list:
            for match_id, line in enumerate(match_list):
                if line != '' and line[0] != '#':  # if the line isn't empty or escaped, we've got a match to play
                    next_match = self.FileMatch(self._config, match_id, line)
                    break

        return next_match

    def submit_result(self, match: FileMatch, result):
        with open("results", "w+") as map_file:
            map_file.write(str(result) + "\n\n")

        result_type = "Error"  # avoid error from this not being initialized
        result_json = {
            "Bot1": match.bot1.name,
            "Bot2": match.bot2.name,
            "Winner": None,
            "Map": None,
            "Result": None,
            "GameTime": None,
            "GameTimeFormatted": None,
            "TimeStamp": None,
            "Bot1AvgFrame": 0,
            "Bot2AvgFrame": 0,
        }
        if isinstance(result, list):
            for x in result:
                if x.get("Result", None):
                    temp_results = x["Result"]
                    # self._utl.printout(str(temp_results))

                    if temp_results[match.bot1.name] == "Result.Crashed":
                        result_type = "Player1Crash"
                        result_json["Winner"] = match.bot2.name

                    elif temp_results[match.bot2.name] == "Result.Crashed":
                        result_type = "Player2Crash"
                        result_json["Winner"] = match.bot1.name

                    elif temp_results[match.bot1.name] == "Result.Timeout":
                        result_type = "Player1TimeOut"
                        result_json["Winner"] = match.bot2.name

                    elif temp_results[match.bot2.name] == "Result.Timeout":
                        result_type = "Player2TimeOut"
                        result_json["Winner"] = match.bot1.name

                    elif temp_results[match.bot1.name] == "Result.Victory":
                        result_type = "Player1Win"
                        result_json["Winner"] = match.bot1.name

                    elif temp_results[match.bot1.name] == "Result.Defeat":
                        result_type = "Player2Win"
                        result_json["Winner"] = match.bot2.name

                    elif temp_results[match.bot1.name] == "Result.Tie":
                        result_type = "Tie"
                        result_json["Winner"] = "Tie"

                    else:
                        result_type = "InitializationError"

                    result_json["Result"] = result_type

                if x.get("GameTime", None):
                    result_json["GameTime"] = x["GameTime"]
                    result_json["GameTimeFormatted"] = x["GameTimeFormatted"]

                if x.get("AverageFrameTime", None):
                    try:
                        result_json["Bot1AvgFrame"] = next(
                            item[match.bot1.name] for item in x['AverageFrameTime'] if item.get(match.bot1.name, None))
                    except StopIteration:
                        result_json["Bot1AvgFrame"] = 0
                    try:
                        result_json["Bot2AvgFrame"] = next(
                            item[match.bot2.name] for item in x['AverageFrameTime'] if item.get(match.bot2.name, None))
                    except StopIteration:
                        result_json["Bot2AvgFrame"] = 0

                if x.get("TimeStamp", None):
                    result_json["TimeStamp"] = x["TimeStamp"]
        else:
            result_json["Result"] = result_type

        filename = Path(self._results_file)
        filename.touch(exist_ok=True)  # will create file, if it exists will do nothing

        with open(self._results_file, "r+") as results_log:
            try:
                results = json.loads(results_log.read())
                result_list = results['Results']
                result_list.append(result_json)
                results_log.seek(0)
                json_object = dict({"Results": result_list})
                results_log.write(json.dumps(json_object, indent=4))
            except:
                results_log.seek(0)
                json_object = dict({"Results": [result_json]})
                results_log.write(json.dumps(json_object, indent=4))

        # remove the played match from the match list
        with open(self._matches_file, "r") as match_list:
            lines = match_list.readlines()

        lines[match.id] = '# ' + lines[match.id]

        with open(self._matches_file, "w") as match_list:
            match_list.writelines(lines)


class MatchSourceFactory:
    """
    Builds MatchSources
    """

    @staticmethod
    def build_match_source(config) -> MatchSource:
        if config.MATCH_SOURCE_CONFIG.TYPE == MatchSourceType.FILE:
            return FileMatchSource(config, config.MATCH_SOURCE_CONFIG)
        elif config.MATCH_SOURCE_CONFIG.TYPE == MatchSourceType.HTTP_API:
            return HttpApiMatchSource(config.MATCH_SOURCE_CONFIG, config)
        else:
            raise NotImplementedError()
