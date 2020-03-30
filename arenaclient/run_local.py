import asyncio
from multiprocessing import Process
from typing import List

from collections import deque

from arenaclient.proxy.frontend import GameRunner
from arenaclient.proxy.server import run_server


class RunLocal:
    def __init__(self):
        self.server_process = None
        # Realtime and visualize setting, e.g. {"Realtime": False, "Visualize": False}
        self.data = {}
        # List of games, e.g. ["basic_bot,T,python,loser_bot,T,python,AcropolisLE"]
        self.games_queue = deque()
        self.runner = GameRunner()

    def start_server(self):
        """
        Start server
        """
        self.server_process = Process(target=run_server, args=(False,))
        self.server_process.daemon = True
        self.server_process.start()

    def stop_server(self):
        """
        Stop server
        """
        self.server_process.terminate()

    def __enter__(self):
        self.start_server()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop_server()

    def add_games_to_queue(self, games: List[str]):
        """

        @param games:
        """
        for game in games:
            self.games_queue.append(game)

    def generate_games_list(self, bot1_list: List[str], bot2_list: List[str], map_list: List[str]) -> List[str]:
        """
        Generates games list, every bot from 'bot1_list' will be matched against every bot from 'bot2_list' on every map
        in 'map_list'.

        Example input:
            generate_games_list(["CreepyBot,Z,python"], ["basic_bot,T,python", "loser_bot,T,python],
            ["AcropolisLE", "TritonLE"])
        """
        games = []
        for bot1_string in bot1_list:
            for bot2_string in bot2_list:
                for map_name in map_list:
                    games.append(",".join([bot1_string, bot2_string, map_name]))
        return games

    async def run_local_games(self):
        while self.games_queue:
            games = [self.games_queue.popleft()]
            await self.runner.run_local_game(games, self.data)


async def main():
    # Alternatively you can use start_server() and stop_server()
    with RunLocal() as run_local:
        # Not needed, default: realtime=False and visualize=False
        run_local.data = {"Realtime": False, "Visualize": False}

        # Generate some games list
        bot1_list = ["basic_bot,T,python"]
        bot2_list = ["loser_bot,T,python"]
        map_list = ["AcropolisLE"]
        games = run_local.generate_games_list(bot1_list, bot2_list, map_list)
        # games = ["basic_bot,T,python,loser_bot,T,python,AcropolisLE"]

        # Add games to queue
        run_local.add_games_to_queue(games)

        await run_local.run_local_games()


if __name__ == "__main__":
    # Python 3.7+
    asyncio.run(main())
