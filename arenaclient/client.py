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

from arenaclient.bot import Bot
from arenaclient.matches import MatchSourceFactory
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

    def get_opponent_id(self, bot_name):
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
        if self._config.RUN_LOCAL:
            match_source = MatchSourceFactory.build_match_source(self._config.MATCH_SOURCE_CONFIG)
            match = match_source.next_match()
            if match is None:
                return True  # return True here, else we could end up in an infinite loop
            self._utl.printout(f"Next match: {match.id}")
            result = await self.run_match(
                match_count,
                match.map_name,
                match.bot1_name, match.bot2_name,
                match.bot1_data, match.bot2_data,
                match.id
            )
            match_source.submit_result(match, result)
            return True
        else:
            try:
                next_match_response = requests.post(
                    self._config.API_MATCHES_URL,
                    headers={"Authorization": "Token " + self._config.API_TOKEN},
                )
            except ConnectionError:
                self._utl.printout(
                    f"ERROR: Failed to retrieve game. Connection to website failed. Sleeping."
                )
                time.sleep(30)
                return False

            if next_match_response.status_code >= 400:
                self._utl.printout(
                    f"ERROR: Failed to retrieve game. Status code: {next_match_response.status_code}. Sleeping."
                )
                time.sleep(30)
                return False

            next_match_data = json.loads(next_match_response.text)

            if "id" not in next_match_data:
                self._utl.printout("No games available - sleeping")
                time.sleep(30)
                return False

            next_match_id = next_match_data["id"]
            self._utl.printout(f"Next match: {next_match_id}")

            # Download map
            map_name = next_match_data["map"]["name"]
            map_url = next_match_data["map"]["file"]
            self._utl.printout(f"Downloading map {map_name}")

            try:
                r = requests.get(map_url)
            except Exception as download_exception:
                self._utl.printout(f"ERROR: Failed to download map {map_name} at URL {map_url}. "
                                   f"Error {download_exception}")
                time.sleep(30)
                return False

            map_path = os.path.join(self._config.SC2_HOME, "maps", f"{map_name}.SC2Map")
            with open(map_path, "wb") as map_file:
                map_file.write(r.content)

            bot_0 = Bot(self._config, next_match_data["bot1"])
            if not bot_0.get_bot_file():
                time.sleep(30)
                return False
            bot_1 = Bot(self._config, next_match_data["bot2"])
            if not bot_1.get_bot_file():
                time.sleep(30)
                return False

            bot_0_name, bot_0_data = bot_0.get_bot_data()
            bot_1_name, bot_1_data = bot_1.get_bot_data()

            result = await self.run_match(
                match_count, map_name, bot_0_name, bot_1_name, bot_0_data, bot_1_data, next_match_id
            )
            # self._utl.printout(result)
            self.post_result(next_match_id, result, bot_0_name, bot_1_name)
            if result == "Error":
                return False
            return True

    def post_result(self, match_id, lm_result, bot_1_name, bot_2_name):
        """
        Extract the actual result from the result received from the match runner and post to the ai-arena website, along
        with the logs.

        :param match_id:
        :param lm_result:
        :param bot_1_name:
        :param bot_2_name:
        :return:
        """
        self.kill_current_server()
        game_time: int = 0
        bot1_avg_step_time: float = 0
        bot2_avg_step_time: float = 0

        if isinstance(lm_result, list):
            for x in lm_result:
                if x.get("Result", None):
                    temp_results = x["Result"]
                    self._utl.printout(str(temp_results))
                    bot_1_name = list(x["Result"].keys())[0]
                    bot_2_name = list(x["Result"].keys())[1]

                    if temp_results[bot_1_name] == "Result.Crashed":
                        result = "Player1Crash"

                    elif temp_results[bot_2_name] == "Result.Crashed":
                        result = "Player2Crash"

                    elif temp_results[bot_1_name] == "Result.Timeout":
                        result = "Player1TimeOut"

                    elif temp_results[bot_2_name] == "Result.Timeout":
                        result = "Player2TimeOut"

                    elif temp_results[bot_1_name] == "Result.Victory":
                        result = "Player1Win"

                    elif temp_results[bot_1_name] == "Result.Defeat":
                        result = "Player2Win"


                    elif temp_results[bot_1_name] == "Result.Tie":
                        result = "Tie"

                    else:
                        result = "InitializationError"
                        game_time = 0
                        bot1_avg_step_time = 0
                        bot2_avg_step_time = 0


                if x.get("GameTime", None):
                    game_time = x["GameTime"]

                if x.get("AverageFrameTime", None):
                    try:
                        bot1_avg_step_time = next(
                            item[bot_1_name] for item in x['AverageFrameTime'] if item.get(bot_1_name, None))
                    except StopIteration:
                        bot1_avg_step_time = 0
                    try:
                        bot2_avg_step_time = next(
                            item[bot_2_name] for item in x['AverageFrameTime'] if item.get(bot_2_name, None))
                    except StopIteration:
                        bot2_avg_step_time = 0

        else:
            result = lm_result
            game_time = 0
            bot1_avg_step_time = 0
            bot2_avg_step_time = 0

        self._utl.printout(str(result))
        replay_file: str = ""
        for file in os.listdir(self._config.REPLAYS_DIRECTORY):
            if file.endswith('.SC2Replay'):
                replay_file = file
                break

        replay_file_path = os.path.join(self._config.REPLAYS_DIRECTORY, replay_file)

        bot1_data_folder = os.path.join(self._config.BOTS_DIRECTORY, bot_1_name, "data")
        bot2_data_folder = os.path.join(self._config.BOTS_DIRECTORY, bot_2_name, "data")
        bot1_error_log = os.path.join(bot1_data_folder, "stderr.log")
        bot1_error_log_tmp = os.path.join(self._config.TEMP_PATH, bot_1_name + "-error.log")
        if os.path.isfile(bot1_error_log):
            shutil.move(bot1_error_log, bot1_error_log_tmp)
        else:
            Path(bot1_error_log_tmp).touch()

        bot2_error_log = os.path.join(bot2_data_folder, "stderr.log")
        bot2_error_log_tmp = os.path.join(self._config.TEMP_PATH, bot_2_name + "-error.log")
        if os.path.isfile(bot2_error_log):
            shutil.move(bot2_error_log, bot2_error_log_tmp)
        else:
            Path(bot2_error_log_tmp).touch()

        zip_file = zipfile.ZipFile(
            os.path.join(self._config.TEMP_PATH, bot_1_name + "-error.zip"), "w"
        )
        zip_file.write(
            os.path.join(self._config.TEMP_PATH, bot_1_name + "-error.log"),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        zip_file.close()

        zip_file = zipfile.ZipFile(
            os.path.join(self._config.TEMP_PATH, bot_2_name + "-error.zip"), "w"
        )
        zip_file.write(
            os.path.join(self._config.TEMP_PATH, bot_2_name + "-error.log"),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        zip_file.close()

        # client logs
        proxy_tmp = os.path.join(self._config.TEMP_PATH, "proxy.log")
        client_tmp = os.path.join(self._config.TEMP_PATH, "client.log")

        if os.path.isfile("proxy.log"):
            shutil.move("proxy.log", proxy_tmp)
        else:
            Path(proxy_tmp).touch()


        if os.path.isfile("client.log"):
            shutil.move("client.log", client_tmp)
        else:
            Path(client_tmp).touch()

        arenaclient_log_zip = os.path.join(self._config.TEMP_PATH, "arenaclient_log.zip")
        zip_file = zipfile.ZipFile(arenaclient_log_zip, "w")
        zip_file.write(proxy_tmp, compress_type=zipfile.ZIP_DEFLATED)
        zip_file.write(client_tmp, compress_type=zipfile.ZIP_DEFLATED)
        zip_file.close()

        # Create downloadable data archives
        if not os.path.isdir(bot1_data_folder):
            os.mkdir(bot1_data_folder)
        shutil.make_archive(
            os.path.join(self._config.TEMP_PATH, bot_1_name + "-data"), "zip", bot1_data_folder
        )
        if not os.path.isdir(bot2_data_folder):
            os.mkdir(bot2_data_folder)
        shutil.make_archive(
            os.path.join(self._config.TEMP_PATH, bot_2_name + "-data"), "zip", bot2_data_folder
        )

        try:  # Upload replay file and bot data archives
            file_list = {
                "bot1_data": open(
                    os.path.join(self._config.TEMP_PATH, f"{bot_1_name}-data.zip"), "rb"
                ),
                "bot2_data": open(
                    os.path.join(self._config.TEMP_PATH, f"{bot_2_name}-data.zip"), "rb"
                ),
                "bot1_log": open(
                    os.path.join(self._config.TEMP_PATH, f"{bot_1_name}-error.zip"), "rb"
                ),
                "bot2_log": open(
                    os.path.join(self._config.TEMP_PATH, f"{bot_2_name}-error.zip"), "rb"
                ),
                "arenaclient_log": open(arenaclient_log_zip, "rb"),
            }

            if os.path.isfile(replay_file_path):
                file_list["replay_file"] = open(replay_file_path, "rb")

            payload = {"type": result, "match": int(match_id), "game_steps": game_time}

            if bot1_avg_step_time is not None:
                payload["bot1_avg_step_time"] = bot1_avg_step_time
            if bot2_avg_step_time is not None:
                payload["bot2_avg_step_time"] = bot2_avg_step_time

            if self._config.DEBUG_MODE:
                self._utl.printout(json.dumps(payload))

            post = requests.post(
                self._config.API_RESULTS_URL,
                files=file_list,
                data=payload,
                headers={"Authorization": "Token " + self._config.API_TOKEN},
            )
            if post is None:
                self._utl.printout("ERROR: Result submission failed. 'post' was None.")
            elif post.status_code >= 400:  # todo: retry?
                self._utl.printout(
                    f"ERROR: Result submission failed. Status code: {post.status_code}."
                )
            else:
                self._utl.printout(result + " - Result transferred")
        except ConnectionError:
            self._utl.printout(f"ERROR: Result submission failed. Connection to website failed.")

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
            shutil.rmtree(os.path.join(self._config.BOTS_DIRECTORY, directory))

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

    async def main(self, map_name: str, bot_0_name: str, bot_1_name: str, bot_0_data, bot_1_data, next_match_id: int):
        """
        Method to interact with the match runner. Sends the config and awaits the result.

        :param map_name:
        :param bot_0_name:
        :param bot_1_name:
        :param bot_0_data:
        :param bot_1_data:
        :param next_match_id:
        :return:
        """
        try:
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
                    "Map": map_name,
                    "MaxGameTime": self._config.MAX_GAME_TIME,
                    "Player1": bot_0_name,
                    "Player2": bot_1_name,
                    "ReplayPath": self._config.REPLAYS_DIRECTORY,
                    "MatchID": next_match_id,
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
                    if not result:
                        result.append(
                            {
                                "Result": {
                                    bot_0_name: "InitializationError",
                                    bot_1_name: "InitializationError",
                                }
                            }
                        )
                    await session.close()
                    break
                if msg.type == aiohttp.WSMsgType.ERROR:
                    self._logger.error(msg)
                else:
                    msg = msg.json()
                    if msg.get("Status", None) == "Connected":
                        
                        self._logger.debug(f"Starting bots...")
                        bot1_process = self.start_bot(
                            bot_0_name, bot_0_data, opponent_id=bot_1_data.get("botID", self.get_opponent_id(bot_0_name))
                        )  # todo opponent_id
                        print(self.get_opponent_id(bot_0_name))
                        msg = await ws.receive_json()

                        if msg.get("Bot", None) == "Connected":
                            bot2_process = self.start_bot(
                                bot_1_name, bot_1_data, opponent_id=bot_0_data.get("botID", self.get_opponent_id(bot_1_name))
                            )  # todo opponent_id
                            print(self.get_opponent_id(bot_1_name))
                        else:
                            self._logger.debug(f"Bot2 crash")
                            result.append(
                                {
                                    "Result": {
                                        bot_0_name: "InitializationError",
                                        bot_1_name: "InitializationError",
                                    }
                                }
                            )
                            try:
                                if bot1_process:
                                    bot1_process.kill()
                                
                                if bot2_process:
                                    bot2_process.kill()
                            except:
                                print(traceback.format_exc())
                            # self._utl.pid_cleanup([bot1_process.pid, bot2_process.pid])
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
                                        bot_0_name: "InitializationError",
                                        bot_1_name: "InitializationError",
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
                                        bot_0_name: "InitializationError",
                                        bot_1_name: "InitializationError",
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
                                        bot_0_name: "InitializationError",
                                        bot_1_name: "InitializationError",
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
                                        bot_0_name: "InitializationError",
                                        bot_1_name: "InitializationError",
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
                                        bot_0_name: "InitializationError",
                                        bot_1_name: "InitializationError",
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
                
        except:
            print(str(traceback.format_exc()))
            self._logger.error(str(traceback.format_exc()))
            result = "Error"
        finally:
            if session:
                try:
                    await session.close()
                except:
                    print(str(traceback.format_exc()))
            if not result:
                result.append({"Result": {"InitializationError"}})
            self._logger.debug(str(result))
            try:
                if bot1_process:
                    bot1_process.kill()
                if bot2_process:
                    bot2_process.kill()
            except:
                print(traceback.format_exc())
        return result

    def kill_current_server(self, server=False):
        """
        Kills all the processes running on the match runner's port. Also kills any SC2 processes if
        they are still running.

        :return:
        """
        # return None
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

    async def run_match(self, match_count, map_name, bot_0_name, bot_1_name, bot_0_data, bot_1_data, next_match_id):
        """
        Runs the current match and returns the result.

        :param match_count:
        :param map_name:
        :param bot_0_name:
        :param bot_1_name:
        :param bot_0_data:
        :param bot_1_data:
        :param next_match_id:
        :return:
        """
        try:
            self._utl.printout(f"Starting game - Round {match_count}")
            self._utl.printout(f"{bot_0_name} vs {bot_1_name}")
            self.kill_current_server()
            # proxy = subprocess.Popen(
            #     self._config.PYTHON + " ./proxy/server.py", cwd=self._config.WORKING_DIRECTORY, shell=True
            # )
            counter = 0
            while counter <= 100:
                time.sleep(1)
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

            result = await self.main(
                    map_name,
                    bot_0_name,
                    bot_1_name,
                    bot_0_data,
                    bot_1_data,
                    next_match_id
                )
        
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

            while count < self._config.ROUNDS_PER_RUN:
                if self._config.CLEANUP_BETWEEN_ROUNDS:
                    self.cleanup()
                if await self.run_next_match(count):
                    count += 1
                else:
                    break

                # if RUN_LOCAL:
                #     with open('matchupList','r+') as ml:
                #         head, tail = ml.read().split('\n', 1)
                #         ml.write(tail)

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
