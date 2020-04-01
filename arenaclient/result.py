import os
from arenaclient.matches import MatchSource


class Result:
    def __init__(self, match: MatchSource.Match, cfg):
        self.match_id = match.id
        self.bot1 = match.bot1.name
        self.bot2 = match.bot2.name
        self.winner = None
        self.map = match.map_name
        self.result = None
        self.game_time = 0
        self.game_time_formatted = None
        self.time_stamp = None
        self.bot1_avg_frame = 0
        self.bot2_avg_frame = 0
        self.replay_path = None
        self._config = cfg
        
    def to_json(self):
        """
        Convert Result object to JSON
        """
        return {
            "MatchID": self.match_id,
            "Bot1": self.bot1,
            "Bot2": self.bot2,
            "Winner": self.winner,
            "Map": self.map,
            "Result": self.result if self.result else "Error",
            "GameTime": self.game_time,
            "GameTimeFormatted": self.game_time_formatted,
            "TimeStamp": self.time_stamp,
            "Bot1AvgFrame": self.bot1_avg_frame,
            "Bot2AvgFrame": self.bot2_avg_frame,
            'ReplayPath': self.replay_path,
        }

    def has_result(self):
        """
        Checks if there is a result already
        """
        return self.result is not None

    def parse_result(self, result):
        """
        Parse result messages into  object
        """
        if result.get("Result", None):
            
            temp_results = result['Result']
            if temp_results == "Error":
                self.result = "Error"
                return

            if temp_results[self.bot1] == "Result.Crashed":
                self.result = "Player1Crash"
                self.winner = self.bot2

            elif temp_results[self.bot2] == "Result.Crashed":
                self.result = "Player2Crash"
                self.winner = self.bot1

            elif temp_results[self.bot1] == "Result.Timeout":
                self.result = "Player1TimeOut"
                self.winner = self.bot2

            elif temp_results[self.bot2] == "Result.Timeout":
                self.result = "Player2TimeOut"
                self.winner = self.bot1

            elif temp_results[self.bot1] == "Result.Victory":
                self.result = "Player1Win"
                self.winner = self.bot1

            elif temp_results[self.bot1] == "Result.Defeat":
                self.result = "Player2Win"
                self.winner = self.bot2

            elif temp_results[self.bot1] == "Result.Tie":
                self.result = "Tie"
                self.winner = "Tie"
            
            elif temp_results[self.bot2] == "Result.Tie":
                self.result = "Tie"
                self.winner = "Tie"

            elif temp_results[self.bot1] == 'InitializationError':
                self.result = "InitializationError"

            elif temp_results[self.bot2] == 'InitializationError':
                self.result = "InitializationError"

        if result.get("GameTime", None):
            self.game_time = result["GameTime"]
            self.game_time_formatted = result["GameTimeFormatted"]

        if result.get("AverageFrameTime", None):
            try:
                self.bot1_avg_frame = next(
                    item[self.bot1] for item in result['AverageFrameTime'] if item.get(self.bot1, None)
                )
            except StopIteration:
                self.bot1_avg_frame = 0
            try:
                self.bot2_avg_frame = next(
                    item[self.bot2] for item in result['AverageFrameTime'] if item.get(self.bot2, None)
                )
            except StopIteration:
                self.bot2_avg_frame = 0

        if result.get("TimeStamp", None):
            self.time_stamp = result["TimeStamp"]

        self.replay_path = os.path.join(
            self._config.REPLAYS_DIRECTORY, f'{self.match_id}_{self.bot1}_vs_{self.bot2}.SC2Replay')
