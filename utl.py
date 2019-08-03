import datetime
import os

from termcolor import colored

import config


def is_number(s):
    try:
        float(s)
        return True
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


# https://www.madebuild.org/blog/?p=30
import os
import platform

# GetExitCodeProcess uses a special exit code to indicate that the process is
# still running.
_STILL_ACTIVE = 259

import psutil

def is_pid_running(pid):
    return pid in (p.pid for p in psutil.process_iter())

# def is_pid_running(pid):
#     return (_is_pid_running_on_windows(pid) if platform.system() == "Windows"
#             else _is_pid_running_on_unix(pid))


def _is_pid_running_on_unix(pid):
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _is_pid_running_on_windows(pid):
    import ctypes.wintypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(1, 0, pid)
    if handle == 0:
        return False

    # If the process exited recently, a pid may still exist for the handle.
    # So, check if we can get the exit code.
    exit_code = ctypes.wintypes.DWORD()
    is_running = (
            kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) == 0)
    kernel32.CloseHandle(handle)

    # See if we couldn't get the exit code or the exit code indicates that the
    # process is still running.
    return is_running or exit_code.value == _STILL_ACTIVE