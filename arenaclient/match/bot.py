import hashlib
from loguru import logger
import os
import zipfile
import requests
from ..utl import Utl
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
            "nodejs": [f"{bot_name}.js", "NodeJS"],
            "Python": ["run.py", "Python"],
            "Wine": [f"{bot_name}.exe", "Wine"],
            "BinaryCpp": [f"{bot_name}", "BinaryCpp"],
            "DotNetCore": [f"{bot_name}.dll", "DotNetCore"],
            "Java": [f"{bot_name}.jar", "Java"],
            "NodeJS": [f"{bot_name}.js", "NodeJS"],
            "WSL": [f"{bot_name}", "WSL"]
        }
        return bot_type_map[bot_type][0], bot_type_map[bot_type][1]

    def __init__(self, config, bot_id, name, game_display_id, bot_zip, bot_zip_md5hash, bot_data, bot_data_md5hash,
                 plays_race, bot_type, bot_directory: str, run_as_user: str):
        self._config = config

        self._logger = logger

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
        self.run_as_user = run_as_user
        self.bot_directory: str = bot_directory
        self.bot_data_directory: str = os.path.join(bot_directory, 'data')

    @property
    def bot_json(self):
        bot_mapped_type = Bot.map_to_type(self.name, self.type)

        return {
            "Race": Bot.RACE_MAP[self.plays_race],
            "FileName": bot_mapped_type[0],
            "Type": bot_mapped_type[1],
            "botID": self.game_display_id,
        }

    @property
    def SECURE_MAPPING(self):
        return {1: self._config.SECURE_PLAYER1_USERNAME, 2: self._config.SECURE_PLAYER2_USERNAME}

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
            self._utl.printout(f"Extracting bot {self.name} to {self.bot_directory}")

            # Extract to bot folder
            with zipfile.ZipFile(bot_download_path, "r") as zip_ref:
                zip_ref.extractall(self.bot_directory)
                if self._config.SECURE_MODE:
                    self._utl.set_secure_mode_permissions(self.bot_directory)

            # # if it's a linux bot, we need to add execute permissions
            # if self.type == "cpplinux":
            #     if secure_mode:
            #         file = os.path.join('/home/', user_name, self.name, self.name)
            #     else:
            #         file = f"bots/{self.name}/{self.name}"
            #     # Chmod 744: rwxr--r--
            #     os.chmod(
            #         file,
            #         stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH,
            #     )

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
            self._utl.printout(f"Extracting data for {self.name} to {self.bot_data_directory}")
            with zipfile.ZipFile(bot_data_path, "r") as zip_ref:
                zip_ref.extractall(self.bot_data_directory)
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
            cmd_line.insert(0, os.path.join(self.bot_directory, bot_file))
        elif bot_type.lower() == "java":
            cmd_line.insert(0, "java")
            cmd_line.insert(1, "-jar")
        elif bot_type.lower() == "nodejs":
            cmd_line.insert(0, "node")
        elif bot_type.lower() == "wsl":
            cmd_line.pop(0)
            cmd_line.insert(0, self._utl.convert_wsl_paths(os.path.join(self.bot_directory, bot_file)))
            cmd_line.insert(0, 'wsl ')
        try:
            os.stat(os.path.join(self.bot_directory, "data"))
        except OSError:
            os.mkdir(os.path.join(self.bot_directory, "data"))
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
                def demote(username):
                    import pwd

                    def demote_function():
                        user = pwd.getpwnam(username)
                        uid = user.pw_uid
                        gid = user.pw_gid
                        os.initgroups(username, gid)
                        os.setgid(gid)
                        os.setuid(uid)
                        os.setpgrp()
                    return demote_function

                with open(os.path.join(self.bot_directory, "data", "stderr.log"), "w+") as out:
                    if self.run_as_user:
                        function = demote(self.run_as_user)
                    else:
                        function = os.setpgrp
                    process = subprocess.Popen(
                        " ".join(cmd_line),
                        stdout=out,
                        stderr=subprocess.STDOUT,
                        cwd=(str(self.bot_directory)),
                        shell=True,
                        preexec_fn=function,
                    )
                return process
            else:
                with open(os.path.join(self.bot_directory, "data", "stderr.log"), "w+") as out:
                    process = subprocess.Popen(
                        " ".join(cmd_line),
                        stdout=out,
                        stderr=subprocess.STDOUT,
                        cwd=(str(self.bot_directory)),
                        shell=False,
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
    def get_bot_directory_and_run_as_user(config, bot_name: str, player_number: int) -> (str, str):
        if config.SECURE_MODE:
            if player_number == 1:
                return os.path.join('/home', config.RUN_PLAYER1_AS_USER), config.RUN_PLAYER1_AS_USER
            elif player_number == 2:
                return os.path.join('/home', config.RUN_PLAYER2_AS_USER), config.RUN_PLAYER2_AS_USER
            else:
                raise Exception("player_number is invalid!")
        else:
            return os.path.join(config.BOTS_DIRECTORY, bot_name), None

    @staticmethod
    def from_api_data(config, data, player_number: int):
        """
        Creates bot from api data
        """
        bot_directory, run_as_user = BotFactory.get_bot_directory_and_run_as_user(config, data["name"], player_number)
        return Bot(config, data["id"], data["name"], data["game_display_id"], data["bot_zip"], data["bot_zip_md5hash"],
                   data["bot_data"], data["bot_data_md5hash"], data["plays_race"], data["type"], bot_directory, run_as_user)

    @staticmethod
    def from_values(config, bot_id, bot_name, bot_race, bot_type):
        """
        Creates bot from values
        """
        return Bot(config, bot_id, bot_name, bot_id, None, None, None, None, bot_race, bot_type,
                   os.path.join(config.BOTS_DIRECTORY, bot_name), None)
