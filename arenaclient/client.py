import datetime
import json
from loguru import logger
import os
import shutil
import signal
import socket
import subprocess
import time
import traceback
import hashlib
import aiohttp
import psutil

from arenaclient.matches import MatchSourceFactory, MatchSource
from arenaclient.utl import Utl
from arenaclient.result import Result


class WrongStatusException(Exception):
    """
    Wrong status custom exception
    """
    pass


class WSClosed(Exception):
    """
    Websocket closed custom exception
    """
    pass


def init_error(match: MatchSource.Match):
    """
    Init error JSON
    """
    return {
            "Result": {
                match.bot1.name: "InitializationError",
                match.bot2.name: "InitializationError",
                }
            }


async def connect(address: str, headers=None):
    """
    Connects to address with headers
    """
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(address, headers=headers)
    return ws, session


def complete(msg):
    """
    Checks if msg status is complete.
    """
    return msg.get("Status", None) == "Complete"


def valid_msg(msg):
    """
    Looks for keywords in the message so that the result can be parsed.
    @param msg:
    @return:
    """
    if 'Result' in msg:
        return True
    elif 'GameTime' in msg:
        return True
    elif 'AverageFrameTime' in msg:
        return True
    else:
        return False


class Client:
    """
    Contains all the functionality necessary to operate as an arena client
    """

    def __init__(self, config):
        self._config = config
        self._utl = Utl(self._config)

        self._logger = logger
        self._match_source = MatchSourceFactory.build_match_source(self._config)
        self._ws: aiohttp.client._WSRequestContextManager = ...
        self._session: aiohttp.ClientSession = ...

    @staticmethod
    def get_opponent_id(bot_name):
        """
        Creates an opponent id from a bot's name.

        @param bot_name:
        @return:
        """
        opp_id = hashlib.md5(bot_name.encode("utf-8")).hexdigest()
        return opp_id[0::2]

    @property
    def error(self):
        """
        Error result.
        """
        return {"Result": "Error"}
    
    def json_config(self, match):
        """
        Game JSON config to be sent to proxy
        """
        return {
            "Config": {
                "Map": match.map_name,
                "MaxGameTime": self._config.MAX_GAME_TIME,
                "Player1": match.bot1.name,
                "Player2": match.bot2.name,
                "ReplayPath": self._config.REPLAYS_DIRECTORY,
                "MatchID": match.id,
                "DisableDebug": "False",
                "MaxFrameTime": self._config.MAX_FRAME_TIME,
                "Strikes": self._config.STRIKES,
                "RealTime": self._config.REALTIME,
                "Visualize": self._config.VISUALIZE
            }
        }
    
    @property
    def address(self):
        """
        Address for proxy.
        """
        return f"http://{self._config.SC2_PROXY['HOST']}:{str(self._config.SC2_PROXY['PORT'])}/sc2api"
    
    @property
    def headers(self):
        """
        Headers to send to proxy.
        """
        return dict({"Supervisor": "true"})

    async def run_next_match(self, match_count: int):
        """
        Retrieve the next match from the ai-arena website API. Runs the match, and posts the result to the ai-arena
        website.

        :param match_count:
        :return:
        """
        self._utl.printout(f'New match started at {time.strftime("%H:%M:%S", time.gmtime(time.time()))}')
        match = self._match_source.next_match()
        if match is None:
            # todo: this needs to return true because otherwise a file based match source will cause an infinite loop
            # todo: work out a way to fix this
            return
        self._utl.printout(f"Next match: {match.id}")
        result = await self.run_match(
            match_count,
            match
        )
        self._match_source.submit_result(match, result)
        return

    def cleanup(self):
        """
        Clean up all the folders and files used for the previous match.

        :return:
        """
        # Files to remove inside these folders
        folders = [self._config.REPLAYS_DIRECTORY, self._config.TEMP_PATH]
        for folder in folders:
            for file in os.listdir(folder):
                file_path = os.path.join(folder, file)
                os.remove(file_path)

        # Remove entire sub folders
        for directory in os.listdir(self._config.BOTS_DIRECTORY):
            shutil.rmtree(os.path.join(self._config.BOTS_DIRECTORY, directory), ignore_errors=True)

        # self._logger.debug(f"Killing current server")
        self.kill_current_server()
    
    async def receive(self):
        """
        Receive a message from the websocket connection.
        @return:
        """
        assert(self._ws is not None)
        msg = await self._ws.receive()
        if msg.type == aiohttp.WSMsgType.CLOSED:
            raise WSClosed("Websocket connection closed")
        return msg.json()
    
    async def send(self, msg: str):
        """
        Send a meesage to the websocket connection
        @param msg:
        @return:
        """
        await self._ws.send_str(msg)

    async def connected(self):
        """
        Check to see if client is connected to websocket server.

        @return:
        """
        msg = await self.receive()

        if msg.get("Status") == "Connected":
            return True
        else:
            raise WrongStatusException(f"Expected Connected Status, got {msg}")

    async def start_bot(self, bot, opponent_id):
        """
        Start the bot with the correct arguments.

        :param bot:
        :param opponent_id:
        :return:
        """
        process = bot.start_bot(opponent_id)

        msg = await self.receive()

        if msg.get("Bot", None) == "Connected":
            return process, process.pid
        else:
            return None, process.pid

    async def main(self, match: MatchSource.Match):
        """
        Method to interact with the match runner. Sends the config and awaits the result.

        :param match:
        :return:
        """
        result = Result(match, self._config)
        bot1_process = None
        bot2_process = None
        pids = []
        try:
            self._ws, self._session = await connect(address=self.address, headers=self.headers)
            await self.send(json.dumps(self.json_config(match)))

            if await self.connected():
                self._logger.debug(f"Starting bots...")
                bot1_process, bot1_pid = await self.start_bot(match.bot1,
                                                              match.bot2.bot_json.get("botID", self.get_opponent_id(
                                                                  match.bot2.name)))
                pids.append(bot1_pid)
                if bot1_process is not None:
                    bot2_process, bot2_pid = await self.start_bot(match.bot2,
                                                                  match.bot1.bot_json.get("botID", self.get_opponent_id(
                                                                      match.bot2.name)))
                    pids.append(bot2_pid)
                    if bot2_process is None:
                        self._logger.debug(f"Failed to launch {match.bot2.name}")
                        result.parse_result(init_error(match))
                        try:
                            bot1_process.communicate(timeout=0.2)
                        except subprocess.TimeoutExpired:
                            pass
                        self._utl.pid_cleanup(pids)
                        await self._ws.close()
                        await self._session.close()
                        return result
                else:
                    self._logger.debug(f"Failed to launch {match.bot1.name}")
                    result.parse_result(init_error(match))
                    self._utl.pid_cleanup(pids)
                    await self._ws.close()
                    await self._session.close()
                    return result

                # Change PID Group
                self._logger.debug(f"Changing PGID")
                self._utl.move_pids(pids)

                # Bot health check
                self._logger.debug(f"Checking if bot is okay")
                if bot1_process.poll():
                    self._logger.debug(f"Bot1 crash")
                    result.parse_result(init_error(match))

                    # Flush stdout
                    try:
                        bot1_process.communicate(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                    try:
                        bot2_process.communicate(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                    self._utl.pid_cleanup(pids)
                    await self._ws.close()
                    await self._session.close()
                    return result

                else:
                    await self.send(json.dumps({"Bot1": True}))

                if bot2_process.poll():
                    self._logger.debug(f"Bot2 crash")
                    result.parse_result(init_error(match))
                    try:
                        bot1_process.communicate(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                    try:
                        bot2_process.communicate(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                    self._utl.pid_cleanup(pids)
                    await self._ws.close()
                    await self._session.close()
                    return result

                else:
                    await self.send(json.dumps({"Bot2": True}))

            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.CLOSED:
                    if not result.has_result():
                        result.parse_result(self.error)
                    return result

                msg = msg.json()

                if "PID" in msg:
                    try:
                        bot1_process.communicate(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                    try:
                        bot2_process.communicate(timeout=0.2)
                    except subprocess.TimeoutExpired:
                        pass
                    self._utl.pid_cleanup(pids)  # Terminate bots first
                    self._utl.pid_cleanup(msg["PID"])  # Terminate SC2 processes

                if valid_msg(msg):
                    result.parse_result(msg)

                if 'Error' in msg:
                    self._utl.printout(msg)
                    if not result.has_result():
                        result.parse_result(self.error)
                    await self._ws.close()
                    await self._session.close()

                if 'StillAlive' in msg:
                    if bot1_process.poll():
                        self._utl.printout("Bot1 Crash")
                        await self._ws.close()
                        await self._session.close()
                        if not result.has_result():
                            result.parse_result(
                                {
                                    "Result": {
                                        match.bot1.name: "Result.Crashed",
                                        match.bot2.name: "Result.Victory",
                                    }
                                }
                            )
                        try:
                            bot1_process.communicate(timeout=0.2)
                        except subprocess.TimeoutExpired:
                            pass
                        try:
                            bot2_process.communicate(timeout=0.2)
                        except subprocess.TimeoutExpired:
                            pass
                        self._utl.pid_cleanup(pids)

                    if bot2_process.poll():
                        self._utl.printout("Bot2 Crash")
                        await self._ws.close()
                        await self._session.close()
                        if not result.has_result():
                            result.parse_result(
                                {
                                        "Result": {
                                            match.bot1.name: "Result.Victory",
                                            match.bot2.name: "Result.Crashed",
                                        }
                                }
                            )
                        try:
                            bot1_process.communicate(timeout=0.2)
                        except subprocess.TimeoutExpired:
                            pass
                        try:
                            bot2_process.communicate(timeout=0.2)
                        except subprocess.TimeoutExpired:
                            pass
                        self._utl.pid_cleanup(pids)

                if complete(msg):
                    result.parse_result(
                        {"TimeStamp": datetime.datetime.utcnow().strftime("%d-%m-%Y %H-%M-%SUTC")}
                    )
                    await self._ws.close()
                    await self._session.close()

            if not result.has_result():
                result.parse_result(init_error(match))

            return result
        except WSClosed:
            print(traceback.format_exc())
            if not result.has_result():
                result.parse_result(self.error)
            return result

    def kill_current_server(self, server=False):
        """
        Kills all the processes running on the match runner's port. Also kills any SC2 processes if
        they are still running.

        :return:
        """
        try:
            if self._config.SYSTEM == "Linux":
                self._utl.printout("Killing SC2")
                os.system("pkill -f SC2_x64")
                if server:
                    os.system("lsof -ti tcp:8765 | xargs kill")
            for process in psutil.process_iter():
                if server:
                    for conns in process.connections(kind="inet"):
                        if conns.laddr.port == self._config.SC2_PROXY["PORT"]:
                            process.send_signal(signal.SIGTERM)
                if process.name() == "SC2_x64.exe":
                    try:
                        process.send_signal(signal.SIGTERM)
                    except psutil.AccessDenied:
                        pass

        except:
            pass

    async def run_match(self, match_count, match: MatchSource.Match):
        """
        Runs the current match and returns the result.

        :param match:
        :param match_count:
        :return:
        """
        try:
            self._utl.printout(f"Starting game - Round {match_count}")
            self._utl.printout(f"{match.bot1.name} vs {match.bot2.name}")
            self.kill_current_server()

            counter = 0
            while counter <= 100:
                counter += 1
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                result = sock.connect_ex(
                    (self._config.SC2_PROXY["HOST"], self._config.SC2_PROXY["PORT"])
                )
                if result == 0:
                    break
                if counter == 100:
                    self._logger.error("Server is not running.")
                    raise
                time.sleep(1)

            result = await self.main(match)

        except Exception:
            self._logger.error(str(traceback.format_exc()))
            result = Result(match, self._config)
            result.parse_result(self.error)

        return result

    async def run(self):
        """
        Run game.
        @return:
        """
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            self._utl.printout(f'Arena Client started at {time.strftime("%H:%M:%S", time.gmtime(time.time()))}')

            os.chdir(self._config.WORKING_DIRECTORY)

            os.makedirs(self._config.REPLAYS_DIRECTORY, exist_ok=True)

            if not self._config.RUN_LOCAL:
                os.makedirs(self._config.TEMP_PATH, exist_ok=True)
                os.makedirs(self._config.BOTS_DIRECTORY, exist_ok=True)

            count = 0

            while self._match_source.has_next() and (
                    count < self._config.ROUNDS_PER_RUN or self._config.ROUNDS_PER_RUN == -1):
                try:
                    if self._config.CLEANUP_BETWEEN_ROUNDS:
                        self.cleanup()

                    await self.run_next_match(count)
                    count += 1

                except Exception as e:
                    self._utl.printout(traceback.format_exc())
                    self._utl.printout(f"arena-client encountered an uncaught exception: {e} Sleeping...")
                    time.sleep(30)

        except Exception as e:
            self._utl.printout(traceback.format_exc())
            self._utl.printout(f"arena-client encountered an uncaught exception during startup: {e} Exiting...")
        finally:
            self.kill_current_server(server=False)
            try:
                if self._config.CLEANUP_BETWEEN_ROUNDS:
                    self.cleanup()
            except:
                pass  # ensure we don't skip the shutdown

            try:
                if self._config.SHUT_DOWN_AFTER_RUN:
                    self._utl.printout("Stopping system")
                    with open(os.path.join(self._config.LOCAL_PATH, ".shutdown"), "w") as f:
                        f.write("Shutdown")
            except:
                self._utl.printout("ERROR: Failed to shutdown.")
