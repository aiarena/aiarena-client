import datetime
import logging
import math
import os
import signal
import time

import psutil
from termcolor import colored


class Utl:
    """
    Class containing helper functions for the AI Arena Client.

    """

    def __init__(self, config):
        self._config = config

        self._logger = logging.getLogger(__name__)
        self._logger.addHandler(config.LOGGING_HANDLER)
        self._logger.setLevel(config.LOGGING_LEVEL)

    @staticmethod
    def is_valid_avg_step_time(num):
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
    
    @staticmethod
    def convert_wsl_paths(path):
        """
        :param path:
        :return:
        """
        new_path = path.replace( 'C:','/mnt/c',).replace('D:','/mnt/d').replace("\\","/").replace(" ", "\ ")
     
        return new_path

    # Needed for hashlib md5 function
    @staticmethod
    def file_as_bytes(file):
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

    @staticmethod
    def is_pid_running(pid):
        """
        Check if PID is running.

        :param pid:
        :return:
        """
        return pid in (p.pid for p in psutil.process_iter())

    @staticmethod
    def check_pid(pid: int):
        """
        Checks if PID is running.

        :param pid:
        :return: bool
        """
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True

    def pid_cleanup(self, pids):
        """
        Kills all the pids passed as a list to this function

        :param pids:
        :return:
        """
        for pid in pids:
            self._logger.debug("Killing: " + str(pid))
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                self._logger.debug("Already closed: " + str(pid))

    @staticmethod
    def move_pids(pids):
        """
        Move the pid/pids to another process group to avoid the bot killing the ai-arena client when closing.
        (CPP API specific)

        :param pids:
        :return:
        """
        if not isinstance(pids, list):
            pids = [pids]
        for pid in pids:
            if pid != 0:
                return
            else:
                for _ in range(0, 5):
                    try:
                        os.setpgid(pid, 0)
                        return
                    except OSError:
                        if os.getpgid(pid) == 0:
                            return
                        time.sleep(0.25)  # sleep for retry

    def kill_current_server(self):
        """
        Kills all the processes running on the match runner's port. Also kills any SC2 processes if they are
        still running.

        :return:
        """
        # return None
        try:
            if self._config.SYSTEM == "Linux":
                self.printout("Killing SC2")
                os.system("pkill -f SC2_x64")
                os.system("lsof -ti tcp:8765 | xargs kill")
            for process in psutil.process_iter():
                for conns in process.connections(kind="inet"):
                    if conns.laddr.port == self._config.SC2_PROXY["PORT"]:
                        process.send_signal(signal.SIGTERM)
                if process.name() == "SC2_x64.exe":
                    process.send_signal(signal.SIGTERM)
        except:
            pass
