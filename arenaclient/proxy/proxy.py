import asyncio
import logging
import socket
import subprocess
import tempfile
import time
import warnings

from arenaclient.proxy.supervisor import Supervisor
import aiohttp
import portpicker
from s2clientprotocol import sc2api_pb2 as sc_pb
from typing import Any
from arenaclient.proxy import maps
from arenaclient.lib import Bot, Controller, Paths, Result

logger = logging.getLogger(__name__)
logger.setLevel(10)
logger.addHandler(logging.FileHandler("proxy.log", "a+"))

warnings.simplefilter("ignore", ResourceWarning)
warnings.simplefilter("ignore", ConnectionResetError)
warnings.simplefilter("ignore", RuntimeWarning)
warnings.simplefilter("ignore", AssertionError)


class Proxy:
    """
    Class for handling all requests/responses between bots and SC2. Receives and sends all relevant
    information(Game config, results etc) from and to the supervisor.
    """

    def __init__(
            self,
            port: int = None,
            game_created: bool = False,
            player_name: str = None,
            opponent_name: str = None,
            max_game_time: int = 60484,
            map_name: str = "AutomatonLE",
            replay_name: str = None,
            disable_debug: bool = False,
            supervisor: Supervisor = None,
            max_frame_time: int = 125,
            strikes: int = 10
    ):
        self.average_time: float = 0
        self.previous_loop: int = 0
        self.current_loop_frame_time: float = 0
        self._surrender: bool = False
        self.player_id: int = 0
        self.joined: bool = False
        self.killed: bool = False
        self.replay_name: str = replay_name
        self.port: int = port
        self.created_game: bool = game_created
        self._result: Any = None
        self.player_name: str = player_name
        self.opponent_name: str = opponent_name
        self.map_name: str = map_name
        self.max_game_time: int = max_game_time
        self.supervisor: Supervisor = supervisor
        self._game_loops: int = 0
        self._game_time_seconds: float = 0
        self.ws_c2p = None
        self.ws_p2s = None
        self.no_of_strikes: int = 0
        self.max_frame_time: int = max_frame_time
        self.strikes: int = strikes
        self.replay_saved: bool = False

    async def __request(self, request):
        """
        Sends a request to SC2 and returns a response
        :param request:
        :return:
        """
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
        """
        Creates a request object from kwargs and return the response from __request.
        :param kwargs:
        :return:
        """
        assert len(kwargs) == 1, "Only one request allowed"

        request = sc_pb.Request(**kwargs)

        response = await self.__request(request)

        if response.error:
            logger.debug(f"{response.error}")

        return response

    async def check_time(self):
        """
        Used for detecting ties. Checks if _game_loops > max_game_time.
        :return:
        """
        if (
                self.max_game_time
                and self._game_loops > self.max_game_time
        ):
            self._result = "Result.Tie"
            self._game_time_seconds = (
                    self._game_loops / 22.4
            )

    async def check_for_result(self):
        """
        Called when game status has moved from in_game. Requests an observation from SC2 and populates self.player_id,
        self._result, self._game_loops from the observation.
        :return:
        """
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
        """
        Static method to send a create_game request to SC2 with the relevant options.
        :param server:
        :param players:
        :param map_name:
        :return:
        """
        logger.debug("Creating game...")
        map_name = map_name.replace(".SC2Replay", "").replace(" ", "")
        response = await server.create_game(maps.get(map_name), players, realtime=False)
        logger.debug("Game created")
        return response

    def _launch(self, host: str, port: int = None, full_screen: bool = False):
        """
        Launches SC2 with the relevant arguments and returns a Popen process.This method also populates self.port if it
        isn't populated already.
        :param host: str
        :param port: int
        :param full_screen: bool
        :return:
        """
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
        """
        Sends a save_replay request to SC2 and writes the response bytes to self.replay_name.
        :return: bool
        """
        if not self.replay_saved:
            logger.debug(f"Requesting replay from server")
            result = await self._execute(save_replay=sc_pb.RequestSaveReplay())
            if len(result.save_replay.data)>10:
                with open(self.replay_name, "wb") as f:
                    f.write(result.save_replay.data)
                logger.debug(f"Saved replay as " + str(self.replay_name))
            self.replay_saved = True
        return True

    async def process_request(self, msg):
        """
        Inspects and modifies requests. This method populates player_name in the join_game request, so that the bot name
        shows in game. Returns serialized message if the request is fine, otherwise returns a bool. This method also
        calls self.save_replay() and sets average_frame_time, game_time and game_time_seconds if a result is available.
        :param msg:
        :return:
        """
        request = sc_pb.Request()
        request.ParseFromString(msg.data)
        try:
            if not self.joined and str(request).startswith("join_game"):
                request.join_game.player_name = self.player_name
                request.join_game.options.raw_affects_selection = True
                self.joined = True
                return request.SerializeToString()

            if request.HasField("debug"):
                return False

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
        """
        Uses responses from SC2 to populate self._game_loops instead of sending extra requests to SC2. Also calls
        self.check_for_result() if the response status is > 3(in_game).
        :param msg:
        :return:
        """
        response = sc_pb.Response()
        response.ParseFromString(msg)
        if response.HasField('observation'):
            self._game_loops = response.observation.observation.game_loop
        if response.status > 3:
            await self.check_for_result()

    async def websocket_handler(self, request, portconfig):
        """
        Handler for all requests. A client session is created for the bot and a connection to SC2 is made to forward
        all requests and responses.
        :param request:
        :param portconfig:
        :return:
        """
        logger.debug("Starting client session")
        start_time = time.monotonic()
        async with aiohttp.ClientSession() as session:
            logger.debug("Websocket client connection starting")
            self.ws_c2p = aiohttp.web.WebSocketResponse(receive_timeout=40)  # Set to 40 to detect internal bot crashes
            await self.ws_c2p.prepare(request)
            request.app["websockets"].add(self.ws_c2p)  # Add bot client to WeakSet for use in detecting amount of
            # clients connected

            logger.debug("Launching SC2")

            players = [
                Bot(None, None, name=self.player_name),
                Bot(None, None, name=self.opponent_name),
            ]

            process = self._launch("127.0.0.1", False)  # This populates self.port

            self.supervisor.pids = process.pid  # Add SC2 to supervisor pid list for use in cleanup

            url = "ws://localhost:" + str(self.port) + "/sc2api"
            logger.debug("Websocket connection: " + str(url))

            while True:  # Gives SC2 a chance to start up. Repeatedly tries to connect to SC2 websocket until it
                # succeeds
                await asyncio.sleep(1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(("127.0.0.1", self.port))
                if result == 0:
                    break
            logger.debug("Connecting to SC2")

            async with session.ws_connect(url) as ws_p2s:  # Connects to SC2 instance
                self.ws_p2s = ws_p2s
                c = Controller(self.ws_p2s, process)
                if not self.created_game:
                    await self.create_game(c, players, self.map_name)
                    self.created_game = True

                logger.debug("Player:" + str(self.player_name))
                logger.debug("Joining game")
                logger.debug(r"Connecting proxy")
                try:
                    async for msg in self.ws_c2p:
                        await self.check_time()  # Check for ties
                        if msg.data is None:
                            raise

                        # Detect slow bots. TODO: Move to own method
                        if self.previous_loop < self._game_loops:  # New loop. Add frame time to average time and reset
                            # current frame time.
                            self.average_time += self.current_loop_frame_time
                            self.previous_loop = self._game_loops

                            if self.current_loop_frame_time * 1000 > self.max_frame_time:  # If bot's current frame is
                                # slower than max allowed, increment strike counter.
                                self.no_of_strikes += 1

                            elif self.no_of_strikes > 0:  # We don't want bots to build up a "credit"
                                self.no_of_strikes -= 1

                            self.current_loop_frame_time = 0

                        else:
                            self.current_loop_frame_time += (time.monotonic() - start_time)

                        if self.no_of_strikes > self.strikes:  # Bot exceeded max_frame_time, surrender on behalf of bot
                            logger.debug(f'{self.player_name} exceeded {self.max_frame_time} ms, {self.no_of_strikes} '
                                         f'times in a row')

                            self._surrender = True
                            self._result = "Result.Timeout"

                        if not self.killed:  # Bot connection has not been closed, forward requests.
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                req = await self.process_request(msg)

                                if isinstance(req, bool):  # If process_request returns a bool, the request has been
                                    # nullified. Return an empty response instead. TODO: Do this better
                                    data_p2s = sc_pb.Response()
                                    data_p2s.id = 0
                                    data_p2s.status = 3
                                    await self.ws_c2p.send_bytes(data_p2s.SerializeToString())
                                else:  # Nothing wrong with the request. Forward to SC2
                                    await self.ws_p2s.send_bytes(req)
                                    try:
                                        data_p2s = await ws_p2s.receive_bytes()  # Receive response from SC2
                                        await self.process_response(data_p2s)
                                    except (
                                            asyncio.CancelledError,
                                            asyncio.TimeoutError,
                                    ) as e:
                                        logger.error(str(e))
                                    await self.ws_c2p.send_bytes(data_p2s)  # Forward response to bot
                                start_time = time.monotonic()  # Start the frame timer.
                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.error("Client shutdown")
                            else:
                                logger.error("Incorrect message type")
                                await self.ws_c2p.close()
                        else:
                            logger.debug("Websocket connection closed")
                            raise

                except Exception as e:
                    logger.error(str(e))
                finally:

                    if not self._result:  # bot crashed, leave instead.
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
