import datetime
import math

import psutil
from termcolor import colored


class Utl:
    """
    Class containing helper functions for the aiarena-client.

    """
    def __init__(self, config):
        self._config = config

    def is_valid_avg_step_time(self, num):
        """
        Validate avg_step_time.

        :param num:
        :return:
        """
        try:
            number = float(num)  # test float conversion
            # reject nan and inf values
            return not math.isnan(number) and not math.isinf(number)
        except ValueError:
            return False

    # Print to console and log
    def printout(self, text):
        """
        Print to screen and log file using colors.

        :param text:
        :return:
        """
        if self._config.RUN_LOCAL:
            self._do_local_printout(text)
        else:
            self._do_printout(text)

    # todo: merge these two print functions
    def _do_printout(self, text):
        now = datetime.datetime.now()
        infos = [
            now.strftime("%b %d %H:%M:%S"),
            self._config.ARENA_CLIENT_ID,
            str(text),
        ]
        # Maps yellow to the first info, red to the second, green for the text
        colors = ["yellow", "red", "green"]
        colored_infos = " ".join(
            colored(info, color) for info, color in zip(infos, colors)
        )
        print(colored_infos)
        with open(self._config.LOG_FILE, "a+") as f:
            line = " ".join(infos) + "\n"
            f.write(line)

    def _do_local_printout(self, text):
        now = datetime.datetime.now()
        infos = [
            now.strftime("%b %d %H:%M:%S"),
            self._config.ARENA_CLIENT_ID,
            str(text),
        ]
        # Maps yellow to the first info, red to the second, green for the text
        colors = ["yellow", "red", "green"]
        colored_infos = " ".join(
            colored(info, color) for info, color in zip(infos, colors)
        )
        print(colored_infos)
        with open(self._config.LOG_FILE, "a+") as f:
            line = " ".join(infos) + "\n"
            f.write(line)

    # Needed for hashlib md5 function

    def file_as_bytes(self, file):
        with file:
            return file.read()

    def load_pid_from_file(self, pid_file):
        """
        Load PID from PID file.

        :param pid_file:
        :return:
        """
        try:
            with open(pid_file, "r") as file:
                try:
                    return int(file.read())
                except ValueError:
                    self.printout(
                        f"ERROR: Failed to convert contents of PID file to integer."
                    )
                    return None
        except Exception as e:
            self.printout(f"ERROR: Failed to read PID file: {e}")
            return None

    def is_pid_running(self, pid):
        """
        Check if PID is running.

        :param pid:
        :return:
        """
        return pid in (p.pid for p in psutil.process_iter())
