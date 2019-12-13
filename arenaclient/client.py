import datetime
import json
import logging
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path
import hashlib
import aiohttp
import psutil
import requests
from requests.exceptions import ConnectionError

from arenaclient.matches import MatchSourceFactory, MatchSource
from arenaclient.utl import Utl


class Client:
    """
    Contains all the functionality necessary to operate as an arena client
    """

    def __init__(self, config):
        self._config = config
        self._utl = Utl(self._config)

        self._logger = logging.getLogger(__name__)
        self._logger.addHandler(self._config.LOGGING_HANDLER)
        self._logger.setLevel(self._config.LOGGING_LEVEL)
        self._match_source = MatchSourceFactory.build_match_source(self._config)

    @staticmethod
    def get_opponent_id(bot_name):
        hexdigest = hashlib.md5(bot_name.encode("utf-8")).hexdigest()
        return hexdigest[0::2]

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

    def start_bot(self, bot_name, bot_data, opponent_id):
        """
        Start the bot with the correct arguments.

        :param bot_data:
        :param bot_name:
        :param opponent_id:
        :return:
        """
        # todo: move to Bot class

        bot_path = os.path.join(self._config.BOTS_DIRECTORY, bot_name)
        bot_file = bot_data["FileName"]
        bot_type = bot_data["Type"]
        cmd_line = [
            bot_file,
            "--GamePort",
            str(self._config.SC2_PROXY["PORT"]),
            "--StartPort",
            str(self._config.SC2_PROXY["PORT"]),
            "--LadderServer",
            self._config.SC2_PROXY["HOST"],
            "--OpponentId",
            str(opponent_id),
        ]
        if bot_type.lower() == "python":
            cmd_line.insert(0, self._config.PYTHON)
        elif bot_type.lower() == "wine":
            cmd_line.insert(0, "wine")
        elif bot_type.lower() == "mono":
            cmd_line.insert(0, "mono")
        elif bot_type.lower() == "dotnetcore":
            cmd_line.insert(0, "dotnet")
        elif bot_type.lower() == "commandcenter":
            raise
        elif bot_type.lower() == "binarycpp":
            cmd_line.insert(0, os.path.join(bot_path, bot_file))
        elif bot_type.lower() == "java":
            cmd_line.insert(0, "java")
            cmd_line.insert(1, "-jar")
        elif bot_type.lower() == "nodejs":
            raise

        try:
            os.stat(os.path.join(bot_path, "data"))
        except OSError:
            os.mkdir(os.path.join(bot_path, "data"))
        try:
            os.stat(self._config.REPLAYS_DIRECTORY)
        except OSError:
            os.mkdir(self._config.REPLAYS_DIRECTORY)
        
        if self._config.RUN_LOCAL:
            try:
                os.stat(self._config.BOT_LOGS_DIRECTORY)
            except:
                os.mkdir(self._config.BOT_LOGS_DIRECTORY)

        try:
            if self._config.SYSTEM == "Linux":
                with open(os.path.join(bot_path, "data", "stderr.log"), "w+") as out:
                    process = subprocess.Popen(
                        " ".join(cmd_line),
                        stdout=out,
                        stderr=subprocess.STDOUT,
                        cwd=(str(bot_path)),
                        shell=True,
                        preexec_fn=os.setpgrp,
                    )
                return process
            else:
                with open(os.path.join(bot_path, "data", "stderr.log"), "w+") as out:
                    process = subprocess.Popen(
                        " ".join(cmd_line),
                        stdout=out,
                        stderr=subprocess.STDOUT,
                        cwd=(str(bot_path)),
                        shell=True,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    )
                return process
        except Exception as exception:
            self._utl.printout(exception)
            sys.exit(0)

    async def main(self, match: MatchSource.Match):
        """
        Method to interact with the match runner. Sends the config and awaits the result.

        :param match:
        :return:
        """
        result = []
        bot1_process = None
        bot2_process = None

        session = aiohttp.ClientSession()
        ws = await session.ws_connect(
            f"http://{self._config.SC2_PROXY['HOST']}:{str(self._config.SC2_PROXY['PORT'])}/sc2api",
            headers=dict({"Supervisor": "true"}),
        )
        json_config = {
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

        await ws.send_str(json.dumps(json_config))

        while True:
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.CLOSED:
                result.append(
                    {
                        "Result": {
                            match.bot1.name: "InitializationError",
                            match.bot2.name: "InitializationError",
                        }
                    }
                )
                await session.close()
                break
            msg = msg.json()
            if msg.get("Status", None) == "Connected":
                self._logger.debug(f"Starting bots...")
                bot1_process = self.start_bot(
                    match.bot1.name, match.bot1.bot_json,
                    opponent_id=match.bot2.bot_json.get("botID", self.get_opponent_id(match.bot2.name))
                )

                msg = await ws.receive_json()

                if msg.get("Bot", None) == "Connected":
                    bot2_process = self.start_bot(
                        match.bot2.name, match.bot2.bot_json,
                        opponent_id=match.bot1.bot_json.get("botID", self.get_opponent_id(match.bot2.name))
                    )
                else:
                    self._logger.debug(f"Bot2 crash")
                    result.append(
                        {
                            "Result": {
                                match.bot1.name: "InitializationError",
                                match.bot2.name: "InitializationError",
                            }
                        }
                    )
                    self._utl.pid_cleanup([bot1_process.pid, bot2_process.pid])
                    await session.close()
                    break
                msg = await ws.receive_json()

                if msg.get("Bot", None) == "Connected":
                    self._logger.debug(f"Changing PGID")
                    for x in [bot1_process.pid, bot2_process.pid]:
                        self._utl.move_pid(x)

                else:
                    self._logger.debug(f"Bot2 crash")
                    result.append(
                        {
                            "Result": {
                                match.bot1.name: "InitializationError",
                                match.bot2.name: "InitializationError",
                            }
                        }
                    )
                    self._utl.pid_cleanup([bot1_process.pid, bot2_process.pid])
                    await session.close()
                    break
                self._logger.debug(f"checking if bot is okay")

                if bot1_process.poll():
                    self._logger.debug(f"Bot1 crash")
                    result.append(
                        {
                            "Result": {
                                match.bot1.name: "InitializationError",
                                match.bot2.name: "InitializationError",
                            }
                        }
                    )
                    self._utl.pid_cleanup([bot1_process.pid, bot2_process.pid])
                    await session.close()
                    break

                else:
                    await ws.send_str(json.dumps({"Bot1": True}))

                if bot2_process.poll():
                    self._logger.debug(f"Bot2 crash")
                    result.append(
                        {
                            "Result": {
                                match.bot1.name: "InitializationError",
                                match.bot2.name: "InitializationError",
                            }
                        }
                    )
                    self._utl.pid_cleanup([bot1_process.pid, bot2_process.pid])
                    await session.close()
                    break

                else:
                    await ws.send_str(json.dumps({"Bot2": True}))

            if msg.get("PID", None):
                self._utl.pid_cleanup([bot1_process.pid, bot2_process.pid])  # Terminate bots first
                self._utl.pid_cleanup(msg["PID"])  # Terminate SC2 processes

            if msg.get("Result", None):
                result.append(msg)

            if msg.get("GameTime", None):
                result.append(msg)

            if msg.get("AverageFrameTime", None):
                result.append(msg)

            if msg.get("Error", None):
                self._utl.printout(msg)
                await session.close()
                break

            if msg.get("StillAlive", None):
                if bot1_process.poll():
                    self._utl.printout("Bot1 Init Error")
                    await session.close()
                    # if not self._utl.check_pid(bot1_process.pid) and not len(result) >0:
                    result.append(
                        {
                            "Result": {
                                match.bot1.name: "InitializationError",
                                match.bot2.name: "InitializationError",
                            }
                        }
                    )
                    self._utl.pid_cleanup([bot1_process.pid, bot2_process.pid])
                if bot2_process.poll():
                    self._utl.printout("Bot2 Init Error")
                    await session.close()
                    # if not self._utl.check_pid(bot2_process.pid) and not len(result) >0:
                    result.append(
                        {
                            "Result": {
                                match.bot1.name: "InitializationError",
                                match.bot2.name: "InitializationError",
                            }
                        }
                    )

            if msg.get("Status", None) == "Complete":
                result.append(
                    dict(
                        {
                            "TimeStamp": datetime.datetime.utcnow().strftime(
                                "%d-%m-%Y %H-%M-%SUTC"
                            )
                        }
                    )
                )
                await session.close()
                break
        if not result:
            result.append({"Result": {"InitializationError"}})
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
            result = "Error"

        return result

    async def run(self):
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
