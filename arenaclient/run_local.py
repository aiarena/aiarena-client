import asyncio
from multiprocessing import Process
from typing import List

from arenaclient.proxy.frontend import GameRunner
from arenaclient.proxy.server import run_server


def generate_games_list(bot1_list: List[str], bot2_list: List[str], map_list: List[str]) -> List[str]:
    """
    Generates games list, every bot from 'bot1_list' will be matched against every bot from 'bot2_list' on every map in 'map_list'.

    Example input:
        generate_games_list(["CreepyBot,Z,python"], ["basic_bot,T,python", "loser_bot,T,python], ["AcropolisLE", "TritonLE"])
    """
    games = []
    for bot1_string in bot1_list:
        for bot2_string in bot2_list:
            for map_name in map_list:
                games.append(",".join([bot1_string, bot2_string, map_name]))
    return games


async def main():
    # Start proxy server
    proc = Process(target=run_server, args=[False])
    proc.daemon = True
    proc.start()

    runner = GameRunner()
    bot1_list = ["basic_bot,T,python"]
    bot2_list = ["loser_bot,T,python"]
    map_list = ["AcropolisLE"]
    games = generate_games_list(bot1_list, bot2_list, map_list)
    # games = ["basic_bot,T,python,loser_bot,T,python,AcropolisLE"]

    data = {"Realtime": False, "Visualize": False}
    await runner.run_local_game(games, data)

    # Games have run, but server does not shut down automatically, kill server process
    proc.terminate()


if __name__ == "__main__":
    # Python 3.7+
    asyncio.run(main())
