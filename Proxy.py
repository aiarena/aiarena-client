import asyncio
import json
import logging
import os
import socket
import subprocess
import tempfile
import time
import weakref
from json import JSONDecodeError
import warnings
import aiohttp
import portpicker
from aiohttp import web
from s2clientprotocol import sc2api_pb2 as sc_pb
from sc2 import maps
from sc2.data import ChatChannel, Result
from sc2.paths import Paths
from sc2.portconfig import Portconfig
from lib import Timer, Bot, Controller

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8765))

logger = logging.getLogger(__name__)
logger.addHandler(logging.FileHandler("proxy.log", "a+"))
logger.setLevel(10)
warnings.simplefilter("ignore", ResourceWarning)

warnings.simplefilter("ignore", ConnectionResetError)


class Proxy:
    def __init__(
        self,
        port=None,
        game_created=False,
        player_name=None,
        opponent_name=None,
        max_game_time=60484,
        map_name="AutomatonLE",
        replay_name=None,
        disable_debug=False,
        supervisor=None,
    ):
        self.average_time = []
        self._surrender = False
        self.player_id = None
        self.joined = False
        self.killed = False
        self.url = None
        self.session = None
        self.ws = None
        self.players = 0
        self.proxy_client = None
        self.disable_debug = True
        self.replay_name = replay_name
        if port is not None:
            self.port = port
        else:
            self.port = None
        self.created_game = game_created
        self._result = None
        self.check_for_results_counter = 0
        self.map = None
        if player_name:
            self.player_name = player_name
        else:
            self.player_name = None
        if opponent_name:
            self.opponent_name = opponent_name
        else:
            self.opponent_name = None
        self.map_name = map_name
        self.max_game_time = max_game_time
        self.supervisor = supervisor

    async def __request(self, request):
        try:
            await self.ws_p2s.send_bytes(request.SerializeToString())
        except TypeError:
            logger.debug("Cannot send: SC2 Connection already closed.")

        response = sc_pb.Response()
        try:
            response_bytes = await self.ws_p2s.receive_bytes()
        except TypeError:
            logger.exception("Cannot receive: SC2 Connection already closed.")
        except asyncio.CancelledError:
            try:
                await self.ws_p2s.receive_bytes()
            except asyncio.CancelledError:
                logger.error("Requests must not be cancelled multiple times")

        except Exception as e:
            logger.error(str(e))
        response.ParseFromString(response_bytes)
        return response

    async def _execute(self, **kwargs):
        assert len(kwargs) == 1, "Only one request allowed"

        request = sc_pb.Request(**kwargs)

        response = await self.__request(request)

        if response.error:
            logger.debug(f"{response.error}")

        return response

    async def check_time(self):
        result = await self._execute(observation=sc_pb.RequestObservation())
        if (
                self.max_game_time
                and result.observation.observation.game_loop > self.max_game_time
            ):
                self._result = "Result.Tie"
                self._game_loops = result.observation.observation.game_loop
                self._game_time_seconds = (
                    result.observation.observation.game_loop / 22.4
                )

    async def check_for_result(self):
        request = sc_pb.RequestPing()
        r = await self._execute(ping=request)
        if r.status > 3:
            try:
                result = await self._execute(observation=sc_pb.RequestObservation())
                if not self.player_id:
                    self.player_id = (
                        result.observation.observation.player_common.player_id
                    )

                if result.observation.player_result:
                    player_id_to_result = {
                        pr.player_id: Result(pr.result)
                        for pr in result.observation.player_result
                    }
                    self._result = player_id_to_result[self.player_id]
                    self._game_loops = result.observation.observation.game_loop
                    self._game_time_seconds = (
                        result.observation.observation.game_loop / 22.4
                    )

            except Exception as e:
                logger.error(e)

    async def create_game(self, server, players, map_name):
        logger.debug("Creating game...")
        map_name = map_name.replace(".SC2Replay", "").replace(" ", "")
        response = await server.create_game(maps.get(map_name), players, realtime=False)
        logger.debug("Game created")
        return response

    def _launch(self, host, port=None, fullscreen=False):
        if self.port is None:
            self.port = portpicker.pick_unused_port()
        else:
            self.port = port
        tmp_dir = tempfile.mkdtemp(prefix="SC2_")
        args = [
            str(Paths.EXECUTABLE),
            "-listen",
            host,
            "-port",
            str(self.port),
            "-displayMode",
            "1" if fullscreen else "0",
            "-dataDir",
            str(Paths.BASE),
            "-tempDir",
            tmp_dir,
        ]
        # if logger.getEffectiveLevel() <= logging.DEBUG:
        #    args.append("-verbose")

        return subprocess.Popen(args, cwd=(str(Paths.CWD) if Paths.CWD else None))

    async def save_replay(self):
        logger.debug(f"Requesting replay from server")
        result = await self._execute(save_replay=sc_pb.RequestSaveReplay())
        with open(self.replay_name, "wb") as f:
            f.write(result.save_replay.data)
        logger.debug(f"Saved replay as " + str(self.replay_name))
        return True

    async def process_request(self, msg, process):
        request = sc_pb.Request()
        request.ParseFromString(msg.data)
        try:
            if not self.joined and str(request).startswith("join_game"):
                request.join_game.player_name = self.player_name
                request.join_game.options.raw_affects_selection = True
                self.joined = True
                return request.SerializeToString()

            if (#TODO: Use hasfield()
                self.disable_debug
                and "debug" in str(request)
                and "draw" not in str(request)
            ):
                # response = sc_pb.Response()
                # response.error.append(f"LadderManager: Debug not allowed. Request: {request}")
                message = f"{self.player_name} used a debug command. Surrendering..."
                ch = ChatChannel.Broadcast
                await self._execute(
                    action=sc_pb.RequestAction(
                        actions=[
                            sc_pb.Action(
                                action_chat=sc_pb.ActionChat(
                                    channel=ch.value, message=message
                                )
                            )
                        ]
                    )
                )
                self._surrender = True

                # await ws_c.send_bytes(response.SerializeToString())
                self._result = "Result.UsedDebug"

        except Exception as e:
            logger.debug(f"Exception{e}")
        await self.check_for_result()
        if self._result:
            try:
                if {
                    self.player_name: sum(self.average_time) / len(self.average_time)
                } not in self.supervisor.average_frame_time:
                    self.supervisor.average_frame_time = {
                        self.player_name: sum(self.average_time)
                        / len(self.average_time)
                    }
            except ZeroDivisionError:
                self.supervisor.average_frame_time = {self.player_name: 0}
            self.supervisor.game_time = self._game_loops
            self.supervisor.game_time_seconds = self._game_time_seconds
            if await self.save_replay():
                if self._surrender:
                    await self._execute(leave_game=sc_pb.RequestLeaveGame())
                self.killed = True
                return request.SerializeToString()
        return request.SerializeToString()

    async def process_response(self, msg):
        # response = sc_pb.Response()
        # response.ParseFromString(msg)
        pass

    async def websocket_handler(self, request, portconfig):
        logger.debug("Starting client session")
        start_time = time.monotonic()
        async with aiohttp.ClientSession() as session:
            player = None
            logger.debug("Websocket client connection starting")
            self.ws_c2p = web.WebSocketResponse(receive_timeout=40)

            await self.ws_c2p.prepare(request)
            request.app["websockets"].add(self.ws_c2p)

            logger.debug("Launching SC2")

            players = [
                Bot(None, None, name=self.player_name),
                Bot(None, None, name=self.opponent_name),
            ]

            # This populates self.port
            process = self._launch("127.0.0.1", False)

            self.supervisor.pids = process.pid

            logger.debug("Set SC2 pid")
            url = "ws://localhost:" + str(self.port) + "/sc2api"
            logger.debug("Websocket connection: " + str(url))
            # Gives SC2 a chance to start up. TODO: Find a way by using Popen's functions
            while True:
                await asyncio.sleep(0.2)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(("127.0.0.1", self.port))
                if result == 0:
                    break
            logger.debug("Connecting to SC2")
            # Connects to SC2 instance
            async with session.ws_connect(url) as ws_p2s:
                self.ws_p2s = ws_p2s
                c = Controller(self.ws_p2s, process)
                if not self.created_game:
                    await self.create_game(c, players, self.map_name)
                    player = players[0]
                    logger.debug("Player:" + str(player))
                    self.created_game = True

                if not player:
                    player = players[1]
                logger.debug("Player:" + str(player))
                logger.debug("Joining game")
                logger.debug(r"Connecting proxy")
                counter = 0
                try:
                    async for msg in self.ws_c2p:
                        if counter %1000 ==0:
                            await self.check_time()
                            counter =0
                        counter +=1
                        if msg.data is None:
                            raise
                        self.average_time.append(time.monotonic() - start_time)
                        if not self.killed:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                req = await self.process_request(msg, process)
                                await self.ws_p2s.send_bytes(req)
                                try:
                                    data_p2s = await ws_p2s.receive_bytes()
                                    await self.process_response(data_p2s)
                                except (
                                    asyncio.CancelledError,
                                    asyncio.TimeoutError,
                                ) as e:
                                    logger.error(str(e))
                                await self.ws_c2p.send_bytes(data_p2s)
                                start_time = time.monotonic()
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.error("Client shutdown")
                            else:
                                logger.error("Incorrect message type")
                                await self.ws_c2p.close()
                        else:
                            logger.debug("Websocket connection closed")

                except Exception as e:
                    logger.error(str(e))
                finally:
                    # bot crashed, leave instead.
                    if not self._result:
                        logger.debug("Bot crashed")
                        self._result = "Result.Crashed"
                    try:
                        if await self.save_replay():
                            await self._execute(leave_game=sc_pb.RequestLeaveGame())
                    except:
                        logger.debug("Can't save replay, SC2 already closed")
                    try:
                        if {
                            self.player_name: sum(self.average_time)
                            / len(self.average_time)
                        } not in self.supervisor.average_frame_time:
                            self.supervisor.average_frame_time = {
                                self.player_name: sum(self.average_time)
                                / len(self.average_time)
                            }
                    except ZeroDivisionError:
                        self.supervisor.average_frame_time = {self.player_name: 0}

                    self.supervisor.result = dict({self.player_name: self._result})

                    await self.ws_c2p.close()
                    logger.debug("Disconnected")
                    return self.ws_p2s
            return self.ws_p2s


class ConnectionHandler:
    def __init__(self):
        self.connected_clients = 0
        self.portconfig = None
        self.supervisor = None
        self.result = []

    async def bots_connected(self, args):
        request = args[0]
        expected = args[1]
        if not len(request.app["websockets"]) > expected:
            logger.debug("Bots did not connect in time")
            await self.supervisor.send_message(
                dict({"Bot": "Bot did not connect in time"})
            )
            # await self.supervisor.close()

    async def websocket_handler(self, request):
        if bool(request.headers.get("Supervisor", False)):
            logger.debug("Using supervisor")
            self.supervisor = Supervisor()

            Timer(40, self.bots_connected, args=[request, 1])

            await self.supervisor.websocket_handler(request)

        elif self.supervisor is not None:
            logger.debug("Connecting bot with supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            if len(request.app["websockets"]) == 1:
                # game_created =False forces first player to create game when both players are connected.
                logger.debug("First bot connecting")
                await self.supervisor.send_message({"Bot": "Connected"})

                Timer(40, self.bots_connected, args=[request, 2])

                proxy1 = Proxy(
                    game_created=False,
                    player_name=self.supervisor.player1,
                    opponent_name=self.supervisor.player2,
                    max_game_time=self.supervisor.max_game_time,
                    map_name=self.supervisor.map,
                    replay_name=self.supervisor.replay_name,
                    disable_debug=bool(self.supervisor.disable_debug),
                    supervisor=self.supervisor,
                )
                await proxy1.websocket_handler(request, self.portconfig)

            elif len(request.app["websockets"]) == 2:
                logger.debug("Second bot connecting")
                await self.supervisor.send_message({"Bot": "Connected"})
                proxy2 = Proxy(
                    game_created=True,
                    player_name=self.supervisor.player2,
                    opponent_name=self.supervisor.player1,
                    max_game_time=self.supervisor.max_game_time,
                    map_name=self.supervisor.map,
                    replay_name=self.supervisor.replay_name,
                    disable_debug=bool(self.supervisor.disable_debug),
                    supervisor=self.supervisor,
                )
                await proxy2.websocket_handler(request, self.portconfig)

        else:  # TODO: Implement this for devs running without a supervisor
            logger.debug("Connecting bot without supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            self.connected_clients += 1
            if self.connected_clients == 1:
                # game_created =False forces first player to create game when both players are connected.
                proxy1 = Proxy(game_created=False)
                await proxy1.websocket_handler(request, self.portconfig)
            else:  # This breaks when there are more than 2 connections. TODO: fix
                proxy2 = Proxy(game_created=True)
                await proxy2.websocket_handler(request, self.portconfig)

        return web.WebSocketResponse()


class Supervisor:
    def __init__(self):
        self._pids = []
        self._average_frame_time = []
        self._config = None
        self._map = None
        self._max_game_time = None
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

    @game_time.setter
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
        ws = web.WebSocketResponse()
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


def main():
    app = aiohttp.web.Application()
    app["websockets"] = weakref.WeakSet()
    connection = ConnectionHandler()
    app.router.add_route("GET", "/sc2api", connection.websocket_handler)
    # aiohttp_debugtoolbar.setup(app)
    aiohttp.web.run_app(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
