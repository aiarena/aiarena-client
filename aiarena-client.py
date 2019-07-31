#!/home/aiarena/venv/bin/python
import datetime
import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
import zipfile
from pathlib import Path
from subprocess import DEVNULL

import requests
from requests.exceptions import ConnectionError
from termcolor import colored

try:
    import config
except ImportError as e:
    if e.name == 'config':
        raise Exception('ERROR: No config.py file found.')
    else:
        raise

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


# Get bot file from api by bot id
def getbotfile(bot):
    botname = bot["name"]
    boturl = bot["bot_zip"]
    botmd5 = bot["bot_zip_md5hash"]
    printout(f"Downloading bot {botname}")
    # Download bot and save to .zip
    r = requests.get(boturl, headers={"Authorization": "Token " + config.API_TOKEN})
    bot_download_path = os.path.join(config.TEMP_PATH, botname + ".zip")
    with open(bot_download_path, "wb") as f:
        f.write(r.content)
    # Load bot from .zip to calculate md5
    with open(bot_download_path, "rb") as f:
        calculated_md5 = hashlib.md5(file_as_bytes(f)).hexdigest()
    if botmd5 == calculated_md5:
        printout("MD5 hash matches transferred file...")
        printout(f"Extracting bot {botname} to bots/{botname}")
        # Extract to bot folder
        with zipfile.ZipFile(bot_download_path, "r") as zip_ref:
            zip_ref.extractall(f"bots/{botname}")

        # if it's a linux bot, we need to add execute permissions
        if bot['type'] == 'cpplinux':
            os.chmod(f'bots/{botname}/{botname}', stat.S_IXUSR)

        if getbotdatafile(bot):
            return True
        else:
            return False
    else:
        printout(f"MD5 hash ({botmd5}) does not match transferred file ({calculated_md5})")
        cleanup()
        return False


# Get bot data
def getbotdatafile(bot):
    botname = bot["name"]
    if bot["bot_data"] is None:
        return True

    botdataurl = bot["bot_data"]
    botdatamd5 = bot["bot_data_md5hash"]
    printout(f"Downloading bot data for {botname}")
    # Download bot data and save to .zip
    r = requests.get(botdataurl, headers={"Authorization": "Token " + config.API_TOKEN})
    bot_data_path = os.path.join(config.TEMP_PATH, botname + "-data.zip")
    with open(bot_data_path, "wb") as f:
        f.write(r.content)
    with open(bot_data_path, "rb") as f:
        calculated_md5 = hashlib.md5(file_as_bytes(f)).hexdigest()
    if botdatamd5 == calculated_md5:
        printout("MD5 hash matches transferred file...")
        printout(f"Extracting data for {botname} to bots/{botname}/data")
        with zipfile.ZipFile(bot_data_path, "r") as zip_ref:
            zip_ref.extractall(f"bots/{botname}/data")
        return True
    else:
        printout(f"MD5 hash ({botdatamd5}) does not match transferred file ({calculated_md5})")
        cleanup()
        return False


# Get bot file
def getbotdata(bot):
    botname = bot["name"]
    botrace = bot["plays_race"]
    bottype = bot["type"]
    botid = bot["game_display_id"]

    race_map = {"P": "Protoss", "T": "Terran", "Z": "Zerg", "R": "Random"}
    bot_type_map = {
        "python": ["run.py", "Python"],
        "cppwin32": [f"{botname}.exe", "Wine"],
        "cpplinux": [f"{botname}", "BinaryCpp"],
        "dotnetcore": [f"{botname}.dll", "DotNetCore"],
        "java": [f"{botname}.jar", "Java"],
        "nodejs": ["main.jar", "NodeJS"],
    }

    bot_data = {
        "Race": race_map[botrace],
        "RootPath": os.path.join(config.WORKING_DIRECTORY, f"bots", botname),
        "FileName": bot_type_map[bottype][0],
        "Type": bot_type_map[bottype][1],
        "botID": botid,
    }
    return botname, bot_data


def getnextmatch(count):
    try:
        nextmatchresponse = requests.post(
            config.API_MATCHES_URL, headers={"Authorization": "Token " + config.API_TOKEN}
        )
    except ConnectionError as ce:
        printout(f"ERROR: Failed to retrieve game. Connection to website failed. Sleeping.")
        time.sleep(30)
        return False

    if nextmatchresponse.status_code >= 400:
        printout(f"ERROR: Failed to retrieve game. Status code: {nextmatchresponse.status_code}. Sleeping.")
        time.sleep(30)
        return False

    nextmatchdata = json.loads(nextmatchresponse.text)

    if "id" not in nextmatchdata:
        printout("No games available - sleeping")
        time.sleep(30)
        return False

    nextmatchid = nextmatchdata["id"]
    printout(f"Next match: {nextmatchid}")

    # Download map
    mapname = nextmatchdata["map"]["name"]
    mapurl = nextmatchdata["map"]["file"]
    printout(f"Downloading map {mapname}")

    try:
        r = requests.get(mapurl)
    except:
        printout(f"ERROR: Failed to download map {mapname} at URL {mapurl}.")
        time.sleep(30)
        return False

    map_path = os.path.join(config.SC2_HOME, "maps", f"{mapname}.SC2Map")
    with open(map_path, "wb") as f:
        f.write(r.content)

    bot_0 = nextmatchdata["bot1"]
    if not getbotfile(bot_0):
        time.sleep(30)
        return False
    bot_1 = nextmatchdata["bot2"]
    if not getbotfile(bot_1):
        time.sleep(30)
        return False

    bot_0_name, bot_0_data = getbotdata(bot_0)
    bot_1_name, bot_1_data = getbotdata(bot_1)

    # Write matchuplist file, line should match something like
    # "m1ndbot"vs"m2ndbot" AutomatonLE.SC2Map
    match_line = f'"{bot_0_name}"vs"{bot_1_name}" {mapname}.SC2Map'
    with open("matchuplist", "w") as f:
        f.write(match_line)

    # Write LadderBots.json file
    ladderbots = {"Bots": {bot_0_name: bot_0_data, bot_1_name: bot_1_data}}
    ladderbots_json = json.dumps(ladderbots, indent=4, sort_keys=True)
    bot_0_game_display_id = bot_0_data['botID']
    bot_1_game_display_id = bot_1_data['botID']
    game_display_id = {bot_0_name: bot_0_game_display_id, bot_1_name: bot_1_game_display_id}
    game_display_id_json = json.dumps(game_display_id, indent=4, sort_keys=True)

    with open("LadderBots.json", "w") as f:
        f.write(ladderbots_json)

    with open("playerids", "w") as f:
        f.write(game_display_id_json)

    runmatch(count)

    # Wait for result.json
    while not os.path.exists(config.SC2LADDERSERVER_RESULTS_FILE):
        time.sleep(1)

    if os.path.isfile(config.SC2LADDERSERVER_RESULTS_FILE):
        printout("Game finished")
        postresult(nextmatchdata)

    return True  # success!


def runmatch(count):
    printout(f"Starting Game - Round {count}")
    with open(config.SC2LADDERSERVER_STDOUT_FILE,"wb") as stdout, open(config.SC2LADDERSERVER_STDERR_FILE,"wb") as stderr:
        subprocess.Popen(
            [config.SC2LADDERSERVER_BINARY, "-e", config.SC2_BINARY],
            stdout=stdout,
            stderr=stderr,
        )


def postresult(match):
    # Parse results.json
    with open(config.SC2LADDERSERVER_RESULTS_FILE) as results_json_file:
        resultdata = json.load(results_json_file)
    for p in resultdata["Results"]:
        result = p["Result"]
        gametime = p["GameTime"]
        bot1_avg_step_time = p['Bot1AvgFrame'] if 'Bot1AvgFrame' in p else None
        bot2_avg_step_time = p['Bot2AvgFrame'] if 'Bot2AvgFrame' in p else None

    # Collect the replayfile
    replayfile = ""
    for file in os.listdir(config.REPLAYS_DIRECTORY):
        if file.endswith(".SC2Replay"):
            replayfile = file
            break
    replay_file_path = os.path.join(config.REPLAYS_DIRECTORY, replayfile)
    if config.RUN_REPLAY_CHECK:
        os.system("perl " + os.path.join(config.LOCAL_PATH, "replaycheck.pl") + " " + replay_file_path)

    bot_1_name = match["bot1"]["name"]
    bot_2_name = match["bot2"]["name"]
    bot1_data_folder = os.path.join(config.WORKING_DIRECTORY, "bots", bot_1_name, "data")
    bot2_data_folder = os.path.join(config.WORKING_DIRECTORY, "bots", bot_2_name, "data")

    # Move the error log to temp
    bot1_error_log = os.path.join(bot1_data_folder, "stderr.log")
    bot1_error_log_tmp = os.path.join(config.TEMP_PATH, bot_1_name + "-error.log")
    if os.path.isfile(bot1_error_log):
        shutil.move(bot1_error_log, bot1_error_log_tmp)
    else:
        Path(bot1_error_log_tmp).touch()

    bot2_error_log = os.path.join(bot2_data_folder, "stderr.log")
    bot2_error_log_tmp = os.path.join(config.TEMP_PATH, bot_2_name + "-error.log")
    if os.path.isfile(bot2_error_log):
        shutil.move(bot2_error_log, bot2_error_log_tmp)
    else:
        Path(bot2_error_log_tmp).touch()

    zip_file = zipfile.ZipFile(os.path.join(config.TEMP_PATH, bot_1_name + "-error.zip"), 'w')
    zip_file.write(os.path.join(config.TEMP_PATH, bot_1_name + "-error.log"), compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()

    zip_file = zipfile.ZipFile(os.path.join(config.TEMP_PATH, bot_2_name + "-error.zip"), 'w')
    zip_file.write(os.path.join(config.TEMP_PATH, bot_2_name + "-error.log"), compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()

    # sc2ladderserver logs
    sc2ladderserver_stdout_log_tmp = os.path.join(config.TEMP_PATH, "sc2ladderserver_stdout.log")
    sc2ladderserver_stderr_log_tmp = os.path.join(config.TEMP_PATH, "sc2ladderserver_stderr.log")
    sc2ladderserver_log_zip = os.path.join(config.TEMP_PATH, "sc2ladderserver_log.zip")

    if os.path.isfile(config.SC2LADDERSERVER_STDOUT_FILE):
        shutil.move(config.SC2LADDERSERVER_STDOUT_FILE, sc2ladderserver_stdout_log_tmp)
    else:
        Path(sc2ladderserver_stdout_log_tmp).touch()

    if os.path.isfile(config.SC2LADDERSERVER_STDERR_FILE):
        shutil.move(config.SC2LADDERSERVER_STDERR_FILE, sc2ladderserver_stderr_log_tmp)
    else:
        Path(sc2ladderserver_stderr_log_tmp).touch()

    zip_file = zipfile.ZipFile(sc2ladderserver_log_zip, 'w')
    zip_file.write(sc2ladderserver_stdout_log_tmp, compress_type=zipfile.ZIP_DEFLATED)
    zip_file.write(sc2ladderserver_stderr_log_tmp, compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()

    # Create downloable data archives
    if not os.path.isdir(bot1_data_folder):
        os.mkdir(bot1_data_folder)
    shutil.make_archive(os.path.join(config.TEMP_PATH, bot_1_name + "-data"), "zip", bot1_data_folder)
    if not os.path.isdir(bot2_data_folder):
        os.mkdir(bot2_data_folder)
    shutil.make_archive(os.path.join(config.TEMP_PATH, bot_2_name + "-data"), "zip", bot2_data_folder)

    try:  # Upload replay file and bot data archives
        file_list = {
            "bot1_data": open(os.path.join(config.TEMP_PATH, f"{bot_1_name}-data.zip"), "rb"),
            "bot2_data": open(os.path.join(config.TEMP_PATH, f"{bot_2_name}-data.zip"), "rb"),
            "bot1_log": open(os.path.join(config.TEMP_PATH, f"{bot_1_name}-error.zip"), "rb"),
            "bot2_log": open(os.path.join(config.TEMP_PATH, f"{bot_2_name}-error.zip"), "rb"),
            "arenaclient_log": open(sc2ladderserver_log_zip, "rb"),
        }

        if os.path.isfile(replay_file_path):
            file_list["replay_file"] = open(replay_file_path, "rb")

        payload = {"type": result, "match": int(match["id"]), "game_steps": gametime}

        if bot1_avg_step_time is not None:
            payload["bot1_avg_step_time"] = bot1_avg_step_time
        if bot2_avg_step_time is not None:
            payload["bot2_avg_step_time"] = bot2_avg_step_time

        post = requests.post(config.API_RESULTS_URL, files=file_list, data=payload,
                             headers={"Authorization": "Token " + config.API_TOKEN})
        if post is None:
            printout("ERROR: Result submission failed. 'post' was None.")
        elif post.status_code >= 400:  # todo: retry
            printout(f"ERROR: Result submission failed. Status code: {post.status_code}.")
        else:
            printout(result + " - Result transferred")
    except ConnectionError as ce:
        printout(f"ERROR: Result submission failed. Connection to website failed.")


def cleanup():
    # Files to remove
    files = [
        config.SC2LADDERSERVER_MATCHUP_LIST_FILE,
        config.SC2LADDERSERVER_LADDERBOTS_FILE,
        config.SC2LADDERSERVER_PLAYERIDS_FILE,
        config.SC2LADDERSERVER_RESULTS_FILE,
        config.SC2LADDERSERVER_STDOUT_FILE,
        config.SC2LADDERSERVER_STDERR_FILE,
    ]

    for file in files:
        if os.path.isfile(file):
            os.remove(file)

    # Files to remove inside these folders
    folders = [config.REPLAYS_DIRECTORY, config.TEMP_PATH]
    for folder in folders:
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            os.remove(file_path)

    # Remove entire subfolders
    bots_dir = os.path.join(config.WORKING_DIRECTORY, "bots")
    for dir in os.listdir(bots_dir):
        shutil.rmtree(os.path.join(bots_dir, dir))


try:
    # create directories if they don't exist
    os.makedirs(config.REPLAYS_DIRECTORY, exist_ok=True)
    os.makedirs(config.TEMP_PATH, exist_ok=True)
    os.makedirs(os.path.join(config.WORKING_DIRECTORY, "bots"), exist_ok=True)

    os.chdir(config.WORKING_DIRECTORY)

    count = 0
    while count <= config.ROUNDS_PER_RUN:
        cleanup()
        if getnextmatch(count):
            count += 1

except Exception as e:
    printout(f"arena-client encountered an uncaught exception: {e} Exiting...")
finally:
    try:
        cleanup()  # be polite and try to cleanup
    except:
        pass

try:
    if config.SHUT_DOWN_AFTER_RUN:
        printout("Stopping system")
        with open(os.path.join(config.LOCAL_PATH, ".shutdown"), "w") as f:
            f.write("Shutdown")
except:
    printout("ERROR: Failed to shutdown.")
