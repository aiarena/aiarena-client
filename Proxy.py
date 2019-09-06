import signal
# import aiohttp_debugtoolbar
import asyncio
import json
import logging
import os
import socket
import subprocess
import sys
import tempfile
import time
import weakref
from json import JSONDecodeError
import warnings
import aiohttp
import portpicker
import websockets
from aiohttp import web
from s2clientprotocol import common_pb2 as c_pb
from s2clientprotocol import sc2api_pb2 as sc_pb
from sc2 import client, maps
from sc2.data import ChatChannel, CreateGameError, PlayerType, Race, Result
from sc2.paths import Paths
from sc2.player import Bot, Computer, Human, Observer
from sc2.portconfig import Portconfig
from sc2.protocol import Protocol

HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', 8765))

logger = logging.getLogger(__name__)
logger.addHandler(logging.FileHandler('proxy.log', 'a+'))
logger.setLevel(10)
warnings.simplefilter("ignore",ResourceWarning)

warnings.simplefilter('ignore',ConnectionResetError)

class AbstractPlayer:
    def __init__(self, p_type, race=None, name=None, difficulty=None, ai_build=None, fullscreen=False):
        assert isinstance(
            p_type, PlayerType), f"p_type is of type {type(p_type)}"
        assert name is None or isinstance(
            name, str), f"name is of type {type(name)}"

        self.name = name
        self.type = p_type
        self.fullscreen = fullscreen
        if race is not None:
            self.race = race

        assert difficulty is None
        assert ai_build is None


class Bot(AbstractPlayer):
    def __init__(self, race, ai, name=None, fullscreen=False):
        """
        AI can be None if this player object is just used to inform the
        server about player types.
        """
        super().__init__(PlayerType.Participant, race, name=name, fullscreen=fullscreen)
        self.ai = ai

    def __str__(self):
        if self.name is not None:
            return f"Bot(Unknown, {self.ai}, name={self.name !r})"
        else:
            return f"Bot(Unknown, {self.ai})"


class ProtocolError(Exception):
    @property
    def is_game_over_error(self) -> bool:
        return self.args[0] in ["['Game has already ended']", "['Not supported if game has already ended']"]


class ConnectionAlreadyClosed(ProtocolError):
    pass


class Controller(Protocol):
    def __init__(self, ws, process):
        super().__init__(ws)
        self.__process = process

    @property
    def running(self):
        return self.__process._process is not None

    async def create_game(self, game_map, players, realtime, random_seed=None):
        assert isinstance(realtime, bool)
        req = sc_pb.RequestCreateGame(local_map=sc_pb.LocalMap(
            map_path=str(game_map.relative_path)), realtime=realtime)
        if random_seed is not None:
            req.random_seed = random_seed

        for player in players:
            p = req.player_setup.add()
            p.type = player.type.value
            p.player_name = player.name

        logger.debug("Creating new game")
        logger.debug(f"Map:     {game_map.name}")
        logger.debug(f"Players: {', '.join(str(p) for p in players)}")
        result = await self._execute(create_game=req)
        
        return result


class Proxy:
    def __init__(self, port=None, game_created=False, player_name=None, opponent_name=None, max_game_time=60484, map_name="AutomatonLE", replay_name=None,disable_debug=False, supervisor=None):
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

    async def __request(self, request, ws):
        try:
            await ws.send_bytes(request.SerializeToString())
        except TypeError:
            raise ConnectionAlreadyClosed(
                "Cannot send: Connection already closed.")

        response = sc_pb.Response()
        try:
            response_bytes = await ws.receive_bytes()
        except TypeError:
            logger.exception("Cannot receive: Connection already closed.")
        except asyncio.CancelledError:
            # If request is sent, the response must be received before reraising cancel
            try:
                await ws.receive_bytes()
            except asyncio.CancelledError:
                logger.error(
                    "Requests must not be cancelled multiple times")
                sys.exit(2)
            raise
        except Exception as e:
            logger.error(e)
        response.ParseFromString(response_bytes)
        # TODO: Figure out if bytes + normalized response needed. Could be useful for determining status of game without sending another request.
        return response, response_bytes

    # TODO: Assign ws to member variable. Won't need to pass as parameter anymore
    async def _execute(self, ws, **kwargs):
        assert len(kwargs) == 1, "Only one request allowed"

        request = sc_pb.Request(**kwargs)

        response, response_bytes = await self.__request(request, ws=ws)

        if response.error:
            raise ProtocolError(f"{response.error}")

        return response

    async def create_game(self, server, players, map_name):
        logger.debug('Creating game...')
        map_name = map_name.replace(".SC2Replay", "").replace(" ", "")
        response = await server.create_game(maps.get(map_name),
                                            players, realtime=False)  # TODO: Accept map and realtime as parameters
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
        #if logger.getEffectiveLevel() <= logging.DEBUG:
        #    args.append("-verbose")

        return subprocess.Popen(
            args,
            cwd=(str(Paths.CWD) if Paths.CWD else None),
        )

    # def kill(self, process):
    #     process.kill()

    async def save_replay(self, ws):
        logger.debug(f"Requesting replay from server")
        result = await self._execute(ws=ws, save_replay=sc_pb.RequestSaveReplay())
        with open(self.replay_name, "wb") as f:
            f.write(result.save_replay.data)
        logger.debug(f"Saved replay as " + str(self.replay_name))
        return True

    async def process_request(self, msg, ws, ws_c,process):
        request = sc_pb.Request()
        request.ParseFromString(msg.data)
        try:           
            if 'join_game' in str(request):
                request.join_game.player_name = self.player_name
                # r= await self._execute(ws,join_game=request.join_game)
                # if not r.error:
                #     self.joined = True
                return request.SerializeToString()

            if self.disable_debug and 'debug' in str(request) and 'draw'not in str(request):
                # response = sc_pb.Response()
                # response.error.append(f"LadderManager: Debug not allowed. Request: {request}")
                message = f"{self.player_name} used a debug command. Surrendering..."
                ch = ChatChannel.Broadcast
                await self._execute(ws,
                    action=sc_pb.RequestAction(
                        actions=[sc_pb.Action(action_chat=sc_pb.ActionChat(channel=ch.value, message=message))]
                    )
                )
                self._surrender = True
               
                # await ws_c.send_bytes(response.SerializeToString())
                self._result = 'Result.UsedDebug'

        except Exception as e:
            logger.debug(f'Exception{e}')

        if not self._result:
            try:
                result = await self._execute(ws=ws, observation=sc_pb.RequestObservation())
                if not self.player_id:
                    self.player_id = result.observation.observation.player_common.player_id

                if self.max_game_time and result.observation.observation.game_loop > self.max_game_time:
                    self._result = 'Result.Tie'

                if result.observation.player_result:
                    player_id_to_result = {pr.player_id: Result(
                        pr.result) for pr in result.observation.player_result}
                    self._result = player_id_to_result[self.player_id]
                    self._game_loops = result.observation.observation.game_loop
                    self._game_time_seconds = result.observation.observation.game_loop / 22.4
            
            except Exception as e:
                logger.error(e)

        if self._result:
            try:
                if {self.player_name:sum(self.average_time)/len(self.average_time)} not in self.supervisor.average_frame_time:
                    self.supervisor.average_frame_time = {self.player_name: sum(self.average_time)/len(self.average_time)}
            except ZeroDivisionError:
                self.supervisor.average_frame_time = {self.player_name:0}
            self.supervisor.game_time = self._game_loops
            self.supervisor.game_time_seconds = self._game_time_seconds
            if await self.save_replay(ws):
                if self._surrender:
                    await self._execute(ws,leave_game=sc_pb.RequestLeaveGame())
                self.killed = True
                self.supervisor.result = dict(
                {self.player_name: self._result})
                return request.SerializeToString()
        return request.SerializeToString()
    
    async def process_response(self,msg):
        response = sc_pb.Response()
        response.ParseFromString(msg)
        

    async def websocket_handler(self, request, portconfig):
        logger.debug("Starting client session")
        start_time = time.monotonic()
        async with aiohttp.ClientSession() as session:
            player = None
            logger.debug('Websocket client connection starting')
            ws_c2p = web.WebSocketResponse()

            await ws_c2p.prepare(request)
            request.app['websockets'].add(ws_c2p)

            logger.debug("Connecting to SC2")

            players = [Bot(  # This requires removal of some asserts in the Bot class. TODO: Override Bot class 
                None, None, name=self.player_name), Bot(None, None, name=self.opponent_name)]  # Name could potentially be used in a game to populate the player's name. Doesn't work yet.

            # This populates self.port
            process = self._launch('127.0.0.1', False)
            self.supervisor.pids = process.pid
            logger.debug("Set SC2 pid")
            url = "ws://localhost:"+str(self.port)+"/sc2api"
            logger.debug('Websocket connection: '+str(url))
            # Gives SC2 a chance to start up. TODO: Find a way by using Popen's functions
            while True:
                await asyncio.sleep(1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(('127.0.0.1', self.port))
                if result == 0:
                    break

            # Connects to SC2 instance            
            async with session.ws_connect(url,) as ws_p2s:
                c = Controller(ws_p2s, process)
                # Not working currently. TODO: Figure out how to create clients
                # self.proxy_client = client.Client(ws_p2s)

                if not self.created_game:
                    await self.create_game(c, players, self.map_name)
                    player = players[0]
                    self.created_game = True
                if not player:
                    player = players[1]
                logger.debug("Player:" + str(player))
                logger.debug("Joining game")
                logger.debug(r"Connecting proxy")
                try:
                    async for msg in ws_c2p:
                        self.average_time.append(time.monotonic()-start_time)
                        if not self.killed:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                req = await self.process_request(msg, ws_p2s,ws_c2p, process)
                                await ws_p2s.send_bytes(req)
                                try:
                                    data_p2s = await ws_p2s.receive_bytes()
                                    await self.process_response(data_p2s)
                                except Exception as e:
                                    logger.error(e)
                                await ws_c2p.send_bytes(data_p2s)
                                start_time = time.monotonic()
                        else:
                            logger.debug(
                                "------------------------------------------------------------")
                            logger.debug("Websocket connection closed")
                            logger.debug(
                                "------------------------------------------------------------")
                except Exception as e:
                    logger.debug(e)
                finally:
                    #bot crashed, leave instead.
                    if self._result is None:
                        self._result = 'Result.Crashed'

                    
                    if await self.save_replay(ws_p2s):
                        await self._execute(ws_p2s,leave_game=sc_pb.RequestLeaveGame())
                    try:
                        if {self.player_name:sum(self.average_time)/len(self.average_time)} not in self.supervisor.average_frame_time:
                            self.supervisor.average_frame_time = {self.player_name:sum(self.average_time)/len(self.average_time)}
                    except ZeroDivisionError:
                        self.supervisor.average_frame_time = {self.player_name:0}
                        self.supervisor.result = dict({self.player_name: self._result})
                    
                    for pid in self.supervisor.pids:
                        logger.debug("Killing", pid)
                        try:
                            os.kill(pid, signal.SIGTERM)
                        except Exception as e:
                            logger.debug("Already closed: ", pid)
                    await ws_c2p.close()
                    logger.debug('Disconnected')
                    return ws_p2s
            return ws_p2s


class ConnectionHandler:
    def __init__(self):
        self.connected_clients = 0
        self.portconfig = None
        self.supervisor = None
        self.result = []

    async def websocket_handler(self, request):
        if bool(request.headers.get('Supervisor', False)):
            logger.debug("Using supervisor")
            self.supervisor = Supervisor()
            await self.supervisor.websocket_handler(request)

        elif self.supervisor is not None:
            logger.debug("Connecting bot with supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            if len(request.app['websockets']) == 1:
                # game_created =False forces first player to create game when both players are connected.
                logger.debug("First bot connecting")
                proxy1 = Proxy(game_created=False,
                               player_name=self.supervisor.player1,
                               opponent_name=self.supervisor.player2,
                               max_game_time=self.supervisor.max_game_time,
                               map_name=self.supervisor.map,
                               replay_name=self.supervisor.replay_name,
                               disable_debug = bool(self.supervisor.disable_debug),
                               supervisor=self.supervisor)
                p1_resp = await proxy1.websocket_handler(request, self.portconfig)

            elif len(request.app['websockets']) == 2:
                logger.debug("Second bot connecting")
                proxy2 = Proxy(game_created=True,
                               player_name=self.supervisor.player2,
                               opponent_name=self.supervisor.player1,
                               max_game_time=self.supervisor.max_game_time,
                               map_name=self.supervisor.map,
                               replay_name=self.supervisor.replay_name,
                               disable_debug = bool(self.supervisor.disable_debug),
                               supervisor=self.supervisor)
                p2_resp = await proxy2.websocket_handler(request, self.portconfig)

        else:  # TODO: Implement this for devs running without a supervisor
            logger.debug("Connecting bot without supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            self.connected_clients += 1
            if self.connected_clients == 1:
                # game_created =False forces first player to create game when both players are connected.
                proxy1 = Proxy(game_created=False)
                resp = await proxy1.websocket_handler(request, self.portconfig)
            else:  # This breaks when there are more than 2 connections. TODO: fix
                proxy2 = Proxy(game_created=True)
                resp = await proxy2.websocket_handler(request, self.portconfig)
        

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
    def average_frame_time(self,value):
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

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        request.app['websockets'].add(ws)

        await ws.send_json({"Status": "Connected"})
        async for msg in ws:
            if msg.type in {aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED}:
                await ws.close()
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    config = json.loads(msg.data)
                    config = config.get('Config',None)
                    if config:
                        self._map = config['Map']
                        self._max_game_time = config['MaxGameTime']
                        self._player1 = config['Player1']
                        self._player2 = config['Player2']
                        self._replay_path = config['ReplayPath']
                        self._match_id = config['MatchID']
                        self._replay_name = os.path.join(
                            self._replay_path, f'{self._match_id}_{self.player1}_vs_{self.player2}.SC2Replay')
                        self._disable_debug = config['DisableDebug']
                    # self.config = config

                except JSONDecodeError as e:
                    json_error = {
                        "Error_Description": "Expected JSON", "Error": str(e)}
                    await ws.send_str(json.dumps(json_error))
                    await ws.close()
                except KeyError as e:
                    json_error = {
                        "Error_Description": "Missing config", "Error": str(e)}
                    await ws.send_str(json.dumps(json_error))
                    await ws.close()
                except Exception as e:
                    logger.debug(e)
            counter=0
            while not self._result:
                counter+=1
                if counter%5==0:
                    await ws.send_str(json.dumps({"StillAlive":"True"}))
                await asyncio.sleep(5)

            final_result = {self.player1: next((str(item.get(
                self.player1, None)) for item in self._result if item.get(
                self.player1, None)), "Result.Crashed"), self.player2: next((str(item.get(
                    self.player2, None)) for item in self._result if item.get(
                    self.player2, None)), "Result.Crashed")}
            
            if 'Result.UsedDebug' in final_result.values():#Hacky way to deal with surrenders TODO:Find better way
                for x,y in final_result.items():
                    if y =='Result.Crashed':
                        final_result[x] = 'Result.Victory'

            self._game_time_formatted = self.format_time()
            await ws.send_json(dict({"Result": final_result}))
            await ws.send_json(dict({"PID": self._pids}))
            await ws.send_json(dict({"GameTime":self._game_time,"GameTimeSeconds":self._game_time_seconds,"GameTimeFormatted":self.game_time_formatted}))
            await ws.send_json(dict({"AverageFrameTime":self.average_frame_time}))
            await ws.send_json(dict({"Status": "Complete"}))
        
        for ws in request.app['websockets']:
            await ws.close()
        logger.debug('Websocket connection closed')
        return ws


def main():
    app = aiohttp.web.Application()
    app['websockets'] = weakref.WeakSet()
    connection = ConnectionHandler()
    app.router.add_route('GET', '/sc2api', connection.websocket_handler)
    # aiohttp_debugtoolbar.setup(app)
    aiohttp.web.run_app(app, host=HOST, port=PORT)

if __name__ == '__main__':
    main()
