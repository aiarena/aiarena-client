import asyncio
import logging
import socket
import subprocess
import tempfile
import time
import warnings

import aiohttp
import portpicker
from s2clientprotocol import sc2api_pb2 as sc_pb

import maps
from lib import Bot, Controller, Paths, Result, ChatChannel

logger = logging.getLogger(__name__)
logger.setLevel(10)
logger.addHandler(logging.FileHandler("proxy.log", "a+"))

warnings.simplefilter("ignore", ResourceWarning)
warnings.simplefilter("ignore", ConnectionResetError)
warnings.simplefilter("ignore", RuntimeWarning)
warnings.simplefilter("ignore", AssertionError)


# noinspection PyTypeChecker,PyUnboundLocalVariable,PyUnusedLocal,PyUnusedLocal
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
            max_frame_time=125,
            strikes=10
    ):
        self.average_time = 0
        self.previous_loop = 0
        self.current_loop_frame_time = 0
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
        self.port = port
        self.created_game = game_created
        self._result = None
        self.check_for_results_counter = 0
        self.map = None
        self.player_name = player_name
        self.opponent_name = opponent_name
        self.map_name = map_name
        self.max_game_time = max_game_time
        self.supervisor = supervisor
        self._game_loops = 0
        self._game_time_seconds = 0
        self.ws_c2p = None
        self.ws_p2s = None
        self.game_step = None
        self.no_of_strikes = 0
        self.max_frame_time = max_frame_time
        self.strikes = strikes

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
        # result = await self._execute(observation=sc_pb.RequestObservation())
        if (
                self.max_game_time
                and self._game_loops > self.max_game_time
        ):
            self._result = "Result.Tie"
            self._game_time_seconds = (
                    self._game_loops / 22.4
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

    @staticmethod
    async def create_game(server, players, map_name):
        logger.debug("Creating game...")
        map_name = map_name.replace(".SC2Replay", "").replace(" ", "")
        response = await server.create_game(maps.get(map_name), players, realtime=False)
        logger.debug("Game created")
        return response

    def _launch(self, host, port=None, full_screen=False):
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
            "1" if full_screen else "0",
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

    async def process_request(self, msg):
        request = sc_pb.Request()
        request.ParseFromString(msg.data)
        # try:
        #     if str(request).startswith('step'):
        #         if not self.game_step:
        #             self.game_step = request.step.count
        #         if self.game_step < 2:
        #             request.step.count = 2
        # except:
        #     pass
        try:
            if not self.joined and str(request).startswith("join_game"):
                request.join_game.player_name = self.player_name
                request.join_game.options.raw_affects_selection = True
                self.joined = True
                return request.SerializeToString()

            if request.HasField("debug"):
                return False

            # if (
            #         self.disable_debug
            #         and "debug" in str(request)
            #         and "draw" not in str(request)
            # ):
            #     # response = sc_pb.Response()
            #     # response.error.append(f"LadderManager: Debug not allowed. Request: {request}")
            #     message = f"{self.player_name} used a debug command. Surrendering..."
            #     ch = ChatChannel.Broadcast
            #     await self._execute(
            #         action=sc_pb.RequestAction(
            #             actions=[
            #                 sc_pb.Action(
            #                     action_chat=sc_pb.ActionChat(
            #                         channel=ch.value, message=message
            #                     )
            #                 )
            #             ]
            #         )
            #     )
            #     self._surrender = True
            #
            #     # await ws_c.send_bytes(response.SerializeToString())
            #     self._result = "Result.UsedDebug"

        except Exception as e:
            logger.debug(f"Exception{e}")

        if self._result:
            try:
                if {
                    self.player_name: self.average_time / self._game_loops
                } not in self.supervisor.average_frame_time:
                    self.supervisor.average_frame_time = {
                        self.player_name: self.average_time / self._game_loops
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
        response = sc_pb.Response()
        response.ParseFromString(msg)
        if response.HasField('observation'):
            self._game_loops = response.observation.observation.game_loop
        if response.status > 3:
            await self.check_for_result()

    async def websocket_handler(self, request, portconfig):
        logger.debug("Starting client session")
        start_time = time.monotonic()
        async with aiohttp.ClientSession() as session:
            player = None
            logger.debug("Websocket client connection starting")
            self.ws_c2p = aiohttp.web.WebSocketResponse(receive_timeout=40)
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
            # Gives SC2 a chance to start up.
            while True:
                await asyncio.sleep(1)
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
                    logger.debug("Player:" + str(player))
                    self.created_game = True
                logger.debug("Player:" + str(self.player_name))
                logger.debug("Joining game")
                logger.debug(r"Connecting proxy")
                counter = 0
                try:
                    async for msg in self.ws_c2p:
                        await self.check_time()
                        if msg.data is None:
                            raise
                        if self.previous_loop < self._game_loops:
                            self.average_time += self.current_loop_frame_time
                            self.previous_loop = self._game_loops

                            if self.current_loop_frame_time * 1000 > self.max_frame_time:
                                self.no_of_strikes += 1

                            elif self.no_of_strikes > 0:
                                self.no_of_strikes -= 1

                            self.current_loop_frame_time = 0

                        else:
                            self.current_loop_frame_time += (time.monotonic() - start_time)

                        if self.no_of_strikes > self.strikes:
                            logger.debug(f'{self.player_name} exceeded {self.max_frame_time} ms, {self.no_of_strikes} '
                                         f'times in a row')

                            self._surrender = True
                            self._result = "Result.Timeout"

                        if not self.killed:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                req = await self.process_request(msg)

                                if isinstance(req, bool):
                                    data_p2s = sc_pb.Response()
                                    data_p2s.id = 0
                                    data_p2s.status = 3
                                    await self.ws_c2p.send_bytes(data_p2s.SerializeToString())
                                else:
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
                    except Exception:
                        logger.debug("Can't save replay, SC2 already closed")
                    try:
                        if {
                            self.player_name: self.average_time / self._game_loops
                        } not in self.supervisor.average_frame_time:
                            self.supervisor.average_frame_time = {
                                self.player_name: self.average_time / self._game_loops
                            }
                    except ZeroDivisionError:
                        self.supervisor.average_frame_time = {self.player_name: 0}

                    self.supervisor.result = dict({self.player_name: self._result})

                    await self.ws_c2p.close()
                    logger.debug("Disconnected")
                    return self.ws_p2s
