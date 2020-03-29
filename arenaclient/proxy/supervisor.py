import asyncio
import json
import logging
import os
from json import JSONDecodeError
from arenaclient.proxy.lib import Timer
import aiohttp
import numpy as np
logger = logging.getLogger(__name__)
logger.setLevel(10)
logger.addHandler(logging.FileHandler("proxy.log", "a+"))
logging.info("Logging started")  # Hack to show logging in PyCharm.


class Supervisor:
    """
    Class to interact with proxies and external source. Receives config from external source, forwards to the proxies,
    proxies sets the result and other relevant information in the supervisor, which forwards it back to the external
    source.
    """

    def __init__(self):
        self.images = {}
        self._pids: list = []
        self._average_frame_time: list = []
        self._map: str = ""
        self._max_game_time: int = 0
        self._max_frame_time: int = 0
        self._strikes: int = 0
        self._result: list = []
        self._player1: str = ""
        self._player2: str = ""
        self._replay_path: str = ""
        self._match_id: str = ""
        self._replay_name: str = ""
        self._game_time: float = 0
        self._game_time_seconds: float = 0
        self._game_time_formatted: str = ""
        self._disable_debug: bool = True
        self._ws = None
        self._real_time: bool = False
        self._visualize: bool = False

    @property
    def game_time(self):
        return self._game_time

    @property
    def real_time(self):
        return self._real_time
    
    @property
    def visualize(self):
        return self._visualize

    @game_time.setter
    def game_time(self, value: float):
        self._game_time = value

    @property
    def average_frame_time(self):
        return self._average_frame_time

    @average_frame_time.setter
    def average_frame_time(self, value: float):
        self._average_frame_time.append(value)

    @property
    def disable_debug(self):
        return self._disable_debug

    @property
    def game_time_seconds(self):
        return self._game_time_seconds

    @game_time_seconds.setter
    def game_time_seconds(self, value: float):
        self._game_time_seconds = value

    @property
    def game_time_formatted(self):
        return self._game_time_formatted

    @property
    def pids(self):
        return self._pids

    @pids.setter
    def pids(self, value: int):
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
        """
        Format game time to a hh:mm:ss string.
        :return:
        """
        t = self._game_time_seconds
        return f"{int(t // 60):02}:{int(t % 60):02}"

    async def close(self):
        """
        Closes client connection.
        :return:
        """
        if not self._result:
            await self._ws.send_json(dict({"Result": "Error"}))
        await self._ws.close()

    async def send_message(self, message):
        """
        Sends json message to client.

        :param message:
        :return:
        """
        await self._ws.send_json(message)
    
    async def build_montage(self):
        try:
            images = [x['image'] for x in self.images.values()] 
            scores = [x['score'] for x in self.images.values()] 
        except KeyError:
            images = []
            scores = []
        
        if images:
            col1 = np.hstack(images)
            col2 = np.hstack(scores)
            final = np.vstack([col1, col2])
            
            return final
        else:
            return None
    
    async def results_checker(self, args=None):
        if len(self._result) == 1:
            for x in self._result:
                for key, value in x.items():
                    if value == 'Result.Crashed':
                        if key == self.player1:
                            self._result.append({self.player2: 'Result.Victory'})
                        else:
                            self._result.append({self.player1: 'Result.Victory'})
                        break
    
    async def cleanup(self, request):
        logger.debug("Discarding supervisor")
        request.app["websockets"].discard(self._ws)
        for ws in request.app["websockets"]:
            await ws.close()
        logger.debug("Websocket connection closed")

    async def websocket_handler(self, request):
        """
        Handles all requests, forwards config to proxies and receives results and other relevant information from the
        proxies, which if forwarded to the external source (client).

        :param request:
        :return:
        """
        ws = aiohttp.web.WebSocketResponse()
        self._ws = ws
        await ws.prepare(request)
        if len(request.app["websockets"]) > 0:
            ws_to_close = []
            for x in request.app["websockets"]:
                logger.error("Too many supervisors.")
                await x.close()
                ws_to_close.append(x)
            for x in ws_to_close:
                request.app["websockets"].discard(x)
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
                        self._real_time = config["RealTime"]
                        self._visualize = config["Visualize"]
                        self.images[self.player1] = {}
                        self.images[self.player2] = {}

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

            while not self._result or len(self._result) < 2:  # Wait for result from proxies.
                counter += 1
                if len(self._result) == 1:
                    for x in self._result:
                        for key, value in x.items():
                            if value == 'Result.Crashed':
                                Timer(40, self.results_checker, args=[])
                                break

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

            self._game_time_formatted = self.format_time()
            await ws.send_json(dict({"Result": final_result}))  # Todo: Send everything in one message.
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
            # break
        await self.cleanup(request)
        await self._ws.close()
        # return self._ws
