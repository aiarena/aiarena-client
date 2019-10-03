from enum import Enum

from arenaclient.bot import Bot


class MatchSourceType(Enum):
    FILE = 1
    HTTP_API = 2


class MatchSource:
    """
    Abstract representation of a source of matches for the arena client to run.
    next_match must be implemented
    """

    class Match:
        """
        Abstract representation of a match.
        """
        pass

    def next_match(self) -> Match:
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

    def __init__(self, match_file):
        self._match_file = match_file

    def next_match(self) -> FileMatch:

        next_match = None

        with open(self._match_file, "r") as match_list:
            for match_id, line in enumerate(match_list):
                if line != '':  # if the line isn't empty, we've got a match to play
                    next_match = self.FileMatch(match_id, line)
                    break

        return next_match


class MatchSourceFactory:
    """
    Builds MatchSources
    """

    @staticmethod
    def build_match_source(config) -> MatchSource:
        if config["SOURCE_TYPE"] == MatchSourceType.FILE:
            return FileMatchSource(config["MATCHES_FILE"])
        else:
            raise NotImplementedError()
