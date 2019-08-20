import datetime
import math

import psutil
from termcolor import colored

import config


def is_valid_avg_step_time(num):
    try:
        number = float(num)  # test float conversion
        return not math.isnan(number) and not math.isinf(number)  # reject nan and inf values
    except ValueError:
        return False


# Print to console and log
def printout(text):
    now = datetime.datetime.now()
    infos = [now.strftime("%b %d %H:%M:%S"), config.ARENA_CLIENT_ID, text]
    # Maps yellow to the first info, red to the second, green for the text
    colors = ["yellow", "red", "green"]
    colored_infos = " ".join(colored(info, color) for info, color in zip(infos, colors))
    print(colored_infos)
    with open(config.LOG_FILE, "a+") as f:
        line = " ".join(infos) + "\n"
        f.write(line)


# Needed for hashlib md5 function
def file_as_bytes(file):
    with file:
        return file.read()


def load_pid_from_file(pid_file):
    try:
        with open(pid_file, 'r') as file:
            try:
                return int(file.read())
            except ValueError:
                printout(f"ERROR: Failed to convert contents of PID file to integer.")
                return None
    except Exception as e:
        printout(f"ERROR: Failed to read PID file: {e}")
        return None


def is_pid_running(pid):
    return pid in (p.pid for p in psutil.process_iter())
