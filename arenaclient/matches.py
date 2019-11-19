import json
from enum import Enum
from pathlib import Path
from arenaclient.bot import Bot


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
        def __init__(self):
            self.TYPE = None

    class Match:
        """
        Abstract representation of a match.
        """
        pass

    def __init__(self, config: MatchSourceConfig):
        pass

    def next_match(self) -> Match:
        raise NotImplementedError()

    def submit_result(self, match: Match, result):
        raise NotImplementedError()


class HttpApiMatchSource(MatchSource):
    """
    Represents a source of matches originating from the AI Arena Website HTTP API
    """

    class HttpApiMatch(MatchSource.Match):
        """
        A representation of a match sourced from the AI Arena Website HTTP API.
        """

        def __init__(self, id, bot1, bot2, map):
            self.id = id
            self.bot1 = bot1
            self.bot2 = bot2
            self.map = map

    def next_match(self):
        raise NotImplementedError()


class FileMatchSource(MatchSource):
    """
    Represents a source of matches originating from a local file

    Expected file format:
    Each match should be on it's own line, line so:
    Bot1Name,Bot1Race,Bot1Type,Bot2Name,Bot2Race[T,P,Z,R],Bot2Type,SC2MapName
    """

    MATCH_FILE_VALUE_SEPARATOR = ','

    class FileMatchSourceConfig:
        def __init__(self, matches_file, results_file):
            self.TYPE = MatchSourceType.FILE
            self.MATCHES_FILE = matches_file
            self.RESULTS_FILE = results_file

    class FileMatch(MatchSource.Match):
        """
        A representation of a match sourced from a file.
        """

        def __init__(self, id, file_line):
            match_values = file_line.split(FileMatchSource.MATCH_FILE_VALUE_SEPARATOR)

            self.id = id

            # Bot 1
            self.bot1_name = match_values[0]
            self.bot1_race = match_values[1]
            self.bot1_type = match_values[2]

            # Bot 2
            self.bot2_name = match_values[3]
            self.bot2_race = match_values[4]
            self.bot2_type = match_values[5]

            # Map
            self.map_name = match_values[6][:-1]  # the last character will be the new line, so remove it

        @property
        def bot1_data(self):
            bot_mapped_type = Bot.map_to_type(self.bot1_name, self.bot1_type)

            return {
                "Race": Bot.RACE_MAP[self.bot1_race],
                "FileName": bot_mapped_type[0],
                "Type": bot_mapped_type[1],
                "botID": 1,
            }

        @property
        def bot2_data(self):
            bot_mapped_type = Bot.map_to_type(self.bot2_name, self.bot2_type)

            return {
                "Race": Bot.RACE_MAP[self.bot2_race],
                "FileName": bot_mapped_type[0],
                "Type": bot_mapped_type[1],
                "botID": 2,
            }

    def __init__(self, config: FileMatchSourceConfig):
        self._matches_file = config.MATCHES_FILE
        self._results_file = config.RESULTS_FILE

    def next_match(self) -> FileMatch:

        next_match = None

        with open(self._matches_file, "r") as match_list:
            for match_id, line in enumerate(match_list):
                if line != '':  # if the line isn't empty, we've got a match to play
                    next_match = self.FileMatch(match_id, line)
                    break

        return next_match

    def submit_result(self, match: FileMatch, result):
        with open("results", "w+") as map_file:
            map_file.write(str(result) + "\n\n")

        result_type = "Error"  # avoid error from this not being initialized
        result_json = {
            "Bot1": match.bot1_name,
            "Bot2": match.bot2_name,
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

                    if temp_results[match.bot1_name] == "Result.Crashed":
                        result_type = "Player1Crash"
                        result_json["Winner"] = match.bot2_name

                    elif temp_results[match.bot2_name] == "Result.Crashed":
                        result_type = "Player2Crash"
                        result_json["Winner"] = match.bot1_name

                    elif temp_results[match.bot1_name] == "Result.Timeout":
                        result_type = "Player1TimeOut"
                        result_json["Winner"] = match.bot2_name

                    elif temp_results[match.bot2_name] == "Result.Timeout":
                        result_type = "Player2TimeOut"
                        result_json["Winner"] = match.bot1_name

                    elif temp_results[match.bot1_name] == "Result.Victory":
                        result_type = "Player1Win"
                        result_json["Winner"] = match.bot1_name

                    elif temp_results[match.bot1_name] == "Result.Defeat":
                        result_type = "Player2Win"
                        result_json["Winner"] = match.bot2_name

                    elif temp_results[match.bot1_name] == "Result.Tie":
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
                            item[match.bot1_name] for item in x['AverageFrameTime'] if item.get(match.bot1_name, None))
                    except StopIteration:
                        result_json["Bot1AvgFrame"] = 0
                    try:
                        result_json["Bot2AvgFrame"] = next(
                            item[match.bot2_name] for item in x['AverageFrameTime'] if item.get(match.bot2_name, None))
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
                results=json.loads(results_log.read())
                result_list = results['Results']
                result_list.append(result_json)
                results_log.seek(0)
                json_object = dict({"Results": result_list})
                results_log.write(json.dumps(json_object, indent=4))
            except:
                results_log.seek(0)
                json_object = dict({"Results": [result_json]})
                results_log.write(json.dumps(json_object, indent=4))


class MatchSourceFactory:
    """
    Builds MatchSources
    """

    @staticmethod
    def build_match_source(config) -> MatchSource:
        if config.TYPE == MatchSourceType.FILE:
            return FileMatchSource(config)
        else:
            raise NotImplementedError()
