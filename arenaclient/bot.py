import hashlib
import logging
import os
import stat
import zipfile
import requests
from arenaclient.utl import Utl
import subprocess


class Bot:
    """
    Class for setting up the config for a bot.
    """

    RACE_MAP = {"P": "Protoss", "T": "Terran", "Z": "Zerg", "R": "Random"}

    @staticmethod
    def map_to_type(bot_name, bot_type):
        """
        Map bot type to relevant run commands.
        """
        bot_type_map = {
            "python": ["run.py", "Python"],
            "cppwin32": [f"{bot_name}.exe", "Wine"],
            "cpplinux": [f"{bot_name}", "BinaryCpp"],
            "dotnetcore": [f"{bot_name}.dll", "DotNetCore"],
            "java": [f"{bot_name}.jar", "Java"],
            "nodejs": ["main.jar", "NodeJS"],
            "Python": ["run.py", "Python"],
            "Wine": [f"{bot_name}.exe", "Wine"],
            "BinaryCpp": [f"{bot_name}", "BinaryCpp"],
            "DotNetCore": [f"{bot_name}.dll", "DotNetCore"],
            "Java": [f"{bot_name}.jar", "Java"],
            "NodeJS": ["main.jar", "NodeJS"],
            "WSL": [f"{bot_name}", "WSL"]
        }
        return bot_type_map[bot_type][0], bot_type_map[bot_type][1]

    def __init__(self, config, bot_id, name, game_display_id, bot_zip, bot_zip_md5hash, bot_data, bot_data_md5hash,
                 plays_race, bot_type):
        self._config = config

        self._logger = logging.getLogger(__name__)
        self._logger.addHandler(self._config.LOGGING_HANDLER)
        self._logger.setLevel(self._config.LOGGING_LEVEL)

        self._utl = Utl(self._config)

        self.id = bot_id
        self.name = name
        self.game_display_id = game_display_id
        self.bot_zip = bot_zip
        self.bot_zip_md5hash = bot_zip_md5hash
        self.bot_data = bot_data
        self.bot_data_md5hash = bot_data_md5hash
        self.plays_race = plays_race
        self.type = bot_type

    @property
    def bot_json(self):
        bot_mapped_type = Bot.map_to_type(self.name, self.type)

        return {
            "Race": Bot.RACE_MAP[self.plays_race],
            "FileName": bot_mapped_type[0],
            "Type": bot_mapped_type[1],
            "botID": self.game_display_id,
        }

    def get_bot_file(self):
        """
        Download the bot's folder and extracts it to a specified location.

        :return: bool
        """
        self._utl.printout(f"Downloading bot {self.name}")
        # Download bot and save to .zip
        r = requests.get(
            self.bot_zip, headers={"Authorization": "Token " + self._config.MATCH_SOURCE_CONFIG.API_TOKEN}
        )
        bot_download_path = os.path.join(self._config.TEMP_PATH, self.name + ".zip")
        with open(bot_download_path, "wb") as bot_zip:
            bot_zip.write(r.content)
        # Load bot from .zip to calculate md5
        with open(bot_download_path, "rb") as bot_zip:
            calculated_md5 = hashlib.md5(self._utl.file_as_bytes(bot_zip)).hexdigest()
        if self.bot_zip_md5hash == calculated_md5:
            self._utl.printout("MD5 hash matches transferred file...")
            self._utl.printout(f"Extracting bot {self.name} to bots/{self.name}")
            # Extract to bot folder
            with zipfile.ZipFile(bot_download_path, "r") as zip_ref:
                zip_ref.extractall(f"bots/{self.name}")

            # if it's a linux bot, we need to add execute permissions
            if self.type == "cpplinux":
                # Chmod 744: rwxr--r--
                os.chmod(
                    f"bots/{self.name}/{self.name}",
                    stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH,
                )

            if self.get_bot_data_file():
                return True
            else:
                return False
        else:
            self._utl.printout(
                f"MD5 hash ({self.bot_zip_md5hash}) does not match transferred file ({calculated_md5})"
            )
            return False

    # Get bot data
    def get_bot_data_file(self):
        """
        Download bot's personal data folder and extract to specified location.

        :return: bool
        """
        if self.bot_data is None:
            return True

        self._utl.printout(f"Downloading bot data for {self.name}")
        # Download bot data and save to .zip
        r = requests.get(
            self.bot_data, headers={"Authorization": "Token " + self._config.MATCH_SOURCE_CONFIG.API_TOKEN}
        )
        bot_data_path = os.path.join(self._config.TEMP_PATH, self.name + "-data.zip")
        with open(bot_data_path, "wb") as bot_data_zip:
            bot_data_zip.write(r.content)
        with open(bot_data_path, "rb") as bot_data_zip:
            calculated_md5 = hashlib.md5(self._utl.file_as_bytes(bot_data_zip)).hexdigest()
        if self.bot_data_md5hash == calculated_md5:
            self._utl.printout("MD5 hash matches transferred file...")
            self._utl.printout(f"Extracting data for {self.name} to bots/{self.name}/data")
            with zipfile.ZipFile(bot_data_path, "r") as zip_ref:
                zip_ref.extractall(f"bots/{self.name}/data")
            return True
        else:
            self._utl.printout(
                f"MD5 hash ({self.bot_data_md5hash}) does not match transferred file ({calculated_md5})"
            )
            return False

    def start_bot(self, opponent_id):
        """
        Start the bot with the correct arguments.
        
        :param opponent_id:
        :return:
        """
        # todo: move to Bot class

        bot_path = os.path.join(self._config.BOTS_DIRECTORY, self.name)
        bot_file = self.bot_json["FileName"]
        bot_type = self.bot_json["Type"]
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
            cmd_line.pop(0)
            cmd_line.insert(0, os.path.join(bot_path, bot_file))
        elif bot_type.lower() == "java":
            cmd_line.insert(0, "java")
            cmd_line.insert(1, "-jar")
        elif bot_type.lower() == "nodejs":
            raise
        elif bot_type.lower() == "wsl":
            cmd_line.pop(0)
            cmd_line.insert(0, self._utl.convert_wsl_paths(os.path.join(bot_path, bot_file)))
            cmd_line.insert(0,'wsl ')
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
            except OSError:
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


class BotFactory:
    """
    Factory to create bot object
    """
    @staticmethod
    def from_api_data(config, data):
        """
        Creates bot from api data
        """
        return Bot(config, data["id"], data["name"], data["game_display_id"], data["bot_zip"], data["bot_zip_md5hash"],
                   data["bot_data"], data["bot_data_md5hash"], data["plays_race"], data["type"])

    @staticmethod
    def from_values(config, bot_id, bot_name, bot_race, bot_type):
        """
        Creates bot from values
        """
        return Bot(config, bot_id, bot_name, bot_id, None, None, None, None, bot_race, bot_type)
