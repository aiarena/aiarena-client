#!/home/aiarena/venv/bin/python
import requests
import json
import datetime
from termcolor import colored
import zipfile
import hashlib
import subprocess
from subprocess import DEVNULL
import os
import time
import shutil

global count
count = 0

this_folder = os.path.dirname(__file__)
temppath = "/tmp/aiarena/"
# Make temporary subfolder
os.makedirs(temppath, exist_ok=True)

os.chdir("/home/aiarena/aiarena-client")

# Read config file
with open("/home/aiarena/aiarena-client/aiarena-client.json") as config_file:
    config = json.load(config_file)

# Print to console and log
def printout(text):
    now = datetime.datetime.now()
    infos = [now.strftime("%b %d %H:%M:%S"), config["id"], text]
    # Maps yellow to the first info, red to the second, green for the text
    colors = ["yellow", "red", "green"]
    colored_infos = " ".join(colored(info, color) for info, color in zip(infos, colors))
    print(colored_infos)
    with open("/home/aiarena/aiarena-client/aiarena-client.log", "a+") as f:
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
    r = requests.get(boturl, headers={"Authorization": "Token " + config["token"]})
    bot_download_path = os.path.join(temppath, botname + ".zip")
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
    r = requests.get(botdataurl, headers={"Authorization": "Token " + config["token"]})
    bot_data_path = os.path.join(temppath, botname + "-data.zip")
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
        "RootPath": f"/home/aiarena/aiarena-client/bots/{botname}",
        "FileName": bot_type_map[bottype][0],
        "Type": bot_type_map[bottype][1],
        "botID": botid,
    }
    return botname, bot_data


def getnextmatch():
    global count
    nextmatchresponse = requests.post(
        "https://ai-arena.net/api/arenaclient/matches/", headers={"Authorization": "Token " + config["token"]}
    )
    nextmatchdata = json.loads(nextmatchresponse.text)

    if "id" not in nextmatchdata:
        printout("No games available - sleeping")
        time.sleep(30)
        cleanup()
        count -= 1
        return

    nextmatchid = nextmatchdata["id"]
    printout(f"Next match: {nextmatchid}")

    mapname = nextmatchdata["map"]["name"]
    mapurl = nextmatchdata["map"]["file"]
    r = requests.get(mapurl)
    printout(f"Downloading map {mapname}")
    map_path = f"/home/aiarena/StarCraftII/maps/{mapname}.SC2Map"
    with open(map_path, "wb") as f:
        f.write(r.content)

    bot_0 = nextmatchdata["bot1"]
    if not getbotfile(bot_0):
        count -= 1
        cleanup()
        return
    bot_1 = nextmatchdata["bot2"]
    if not getbotfile(bot_1):
        count -= 1
        cleanup()
        return

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

    runmatch()

    # Wait for result.json
    while not os.path.exists("/home/aiarena/aiarena-client/results.json"):
        time.sleep(1)

    if os.path.isfile("/home/aiarena/aiarena-client/results.json"):
        printout("Game finished")
        postresult(nextmatchdata)


def runmatch():
    printout(f"Starting Game - Round {count}")
    subprocess.Popen(
        ["/home/aiarena/aiarena-client/Sc2LadderServer", "-e", "/home/aiarena/StarCraftII/Versions/Base70154/SC2_x64"],
        stdout=DEVNULL,
        stderr=DEVNULL,
    )


def postresult(match):
    global count
    # Parse results.json
    with open("/home/aiarena/aiarena-client/results.json") as results_json_file:
        resultdata = json.load(results_json_file)
    for p in resultdata["Results"]:
        result = p["Result"]
        gametime = p["GameTime"]

    replay_folder = "/home/aiarena/aiarena-client/replays"

    # Collect the replayfile
    replayfile = ""
    for file in os.listdir(replay_folder):
        if file.endswith(".SC2Replay"):
            replayfile = file
            break
    replay_file_path = os.path.join(replay_folder, replayfile)
    os.system("perl /home/aiarena/aiarena-client/replaycheck.pl " + replay_file_path)

    bot_1_name = match["bot1"]["name"]
    bot_2_name = match["bot2"]["name"]
    bot1_data_folder = f"/home/aiarena/aiarena-client/bots/{bot_1_name}/data"
    bot2_data_folder = f"/home/aiarena/aiarena-client/bots/{bot_2_name}/data"

    # Create downloable data archives
    if not os.path.isdir(bot1_data_folder):
        os.mkdir(bot1_data_folder)
    shutil.make_archive(temppath + match["bot1"]["name"] + "-data", "zip", bot1_data_folder)
    if not os.path.isdir(bot2_data_folder):
        os.mkdir(bot2_data_folder)
    shutil.make_archive(temppath + match["bot2"]["name"] + "-data", "zip", bot2_data_folder)

    results_website = "https://ai-arena.net/api/arenaclient/results/"

    # Upload replay file and bot data archives
    if os.path.isfile(replay_file_path):
        file_list = {
            "replay_file": open(replay_file_path, "rb"),
            "bot1_data": open(temppath + match["bot1"]["name"] + "-data.zip", "rb"),
            "bot2_data": open(temppath + match["bot2"]["name"] + "-data.zip", "rb"),
        }
        payload = {"type": result, "match": int(match["id"]), "duration": gametime}
        post = requests.post(
            results_website, files=file_list, data=payload, headers={"Authorization": "Token " + config["token"]}
        )
        printout(result + " - Result transferred")
    else:
        payload = {"type": result, "match": int(match["id"]), "duration": gametime}
        post = requests.post(results_website, data=payload, headers={"Authorization": "Token " + config["token"]})
        printout(result + " - Result transferred")


def cleanup():
    # Files to remove
    files = [
        "/home/aiarena/aiarena-client/matchuplist",
        "/home/aiarena/aiarena-client/LadderBots.json",
        "/home/aiarena/aiarena-client/playerids",
        "/home/aiarena/aiarena-client/results.json",
    ]

    for file in files:
        if os.path.isfile(file):
            os.remove(file)

    # Files to remove inside these folders
    folders = ["/home/aiarena/aiarena-client/replays", temppath]
    for folder in folders:
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            os.remove(file_path)

    # Remove entire subfolders
    for dir in os.listdir("/home/aiarena/aiarena-client/bots"):
        shutil.rmtree("/home/aiarena/aiarena-client/bots/" + dir)


while count <= config["rounds"]:
    count += 1
    cleanup()
    getnextmatch()

if config["shutdown"] == "true":
    printout("Stopping system")
    with open("/home/aiarena/aiarena-client/.shutdown", "w") as f:
        f.write("Shutdown")
