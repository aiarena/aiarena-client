import asyncio
import json
import logging
import os
from json import JSONDecodeError

import aiohttp


logger = logging.getLogger(__name__)
logger.setLevel(10)
logger.addHandler(logging.FileHandler("proxy.log", "a+"))
logging.info("Logging started")

class Supervisor:
    def __init__(self):
        self._pids = []
        self._average_frame_time = []
        self._config = None
        self._map = None
        self._max_game_time = None
        self._max_frame_time = None
        self._strikes = None
        self._result = []
        self._player1 = None
        self._player2 = None
        self._replay_path = None
        self._game_status = None
        self._match_id = None
        self._replay_name = None
        self._game_time = 0
        self._game_time_seconds = 0
        self._game_time_formatted = None
        self._disable_debug = True
        self._ws = None

    @property
    def game_time(self):
        return self._game_time

    @game_time.setter
    def game_time(self, value):
        self._game_time = value

    @property
    def average_frame_time(self):
        return self._average_frame_time

    @average_frame_time.setter
    def average_frame_time(self, value):
        self._average_frame_time.append(value)

    @property
    def disable_debug(self):
        return self._disable_debug

    @property
    def game_time_seconds(self):
        return self._game_time_seconds

    @game_time_seconds.setter
    def game_time_seconds(self, value):
        self._game_time_seconds = value

    @property
    def game_time_formatted(self):
        return self._game_time_formatted

    @property
    def pids(self):
        return self._pids

    @pids.setter
    def pids(self, value):
        self._pids.append(value)

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, value):
        self._result.append(value)

    @property
    def map(self):
        return self._map

    @property
    def max_game_time(self):
        return self._max_game_time

    @property
    def player1(self):
        return self._player1

    @property
    def player2(self):
        return self._player2

    @property
    def match_id(self):
        return self._match_id

    @property
    def replay_path(self):
        return self._replay_path

    @property
    def replay_name(self):
        return self._replay_name

    @property
    def strikes(self):
        return self._strikes

    @property
    def max_frame_time(self):
        return self._max_frame_time

    def format_time(self):
        t = self._game_time_seconds
        return f"{int(t // 60):02}:{int(t % 60):02}"

    async def close(self):
        if self._result:
            await self._ws.send_json(dict({"Result": "Error"}))
        await self._ws.close()

    async def send_message(self, message):
        await self._ws.send_json(message)

    async def websocket_handler(self, request):
        ws = aiohttp.web.WebSocketResponse()
        self._ws = ws
        await ws.prepare(request)
        request.app["websockets"].add(ws)

        await ws.send_json({"Status": "Connected"})
        async for msg in ws:
            if msg.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                await ws.close()
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    config = json.loads(msg.data)
                    config = config.get("Config", None)
                    if config:
                        self._map = config["Map"]
                        self._max_game_time = config["MaxGameTime"]
                        self._max_frame_time = config["MaxFrameTime"]
                        self._strikes = config["Strikes"]
                        self._player1 = config["Player1"]
                        self._player2 = config["Player2"]
                        self._replay_path = config["ReplayPath"]
                        self._match_id = config["MatchID"]
                        self._replay_name = os.path.join(
                            self._replay_path,
                            f"{self._match_id}_{self.player1}_vs_{self.player2}.SC2Replay",
                        )
                        self._disable_debug = config["DisableDebug"]
                    # self.config = config

                except JSONDecodeError as e:
                    json_error = {"Error_Description": "Expected JSON", "Error": str(e)}
                    await ws.send_str(json.dumps(json_error))
                    await ws.close()
                except KeyError as e:
                    json_error = {
                        "Error_Description": "Missing config",
                        "Error": str(e),
                    }
                    await ws.send_str(json.dumps(json_error))
                    await ws.close()
                except Exception as e:
                    logger.debug(e)
            counter = 0
            while not self._result or len(self._result) < 2:
                counter += 1
                if counter % 100 == 0:
                    await ws.send_str(json.dumps({"StillAlive": "True"}))
                await asyncio.sleep(0.2)

            final_result = {
                self.player1: next(
                    (
                        str(item.get(self.player1, None))
                        for item in self._result
                        if item.get(self.player1, None)
                    ),
                    "Result.Crashed",
                ),
                self.player2: next(
                    (
                        str(item.get(self.player2, None))
                        for item in self._result
                        if item.get(self.player2, None)
                    ),
                    "Result.Crashed",
                ),
            }

            if (
                    "Result.UsedDebug" in final_result.values()
            ):  # Hacky way to deal with surrenders TODO:Find better way
                for x, y in final_result.items():
                    if y == "Result.Crashed":
                        final_result[x] = "Result.Victory"

            self._game_time_formatted = self.format_time()
            await ws.send_json(dict({"Result": final_result}))
            await ws.send_json(dict({"PID": self._pids}))
            await ws.send_json(
                dict(
                    {
                        "GameTime": self._game_time,
                        "GameTimeSeconds": self._game_time_seconds,
                        "GameTimeFormatted": self.game_time_formatted,
                    }
                )
            )
            await ws.send_json(dict({"AverageFrameTime": self.average_frame_time}))
            await ws.send_json(dict({"Status": "Complete"}))

        for ws in request.app["websockets"]:
            await ws.close()
        logger.debug("Websocket connection closed")
        return ws
