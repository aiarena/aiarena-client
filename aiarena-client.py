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
temppath = "/tmp/aiarena/"
if not os.path.isdir(temppath):
    os.mkdir(temppath)

os.chdir("/home/aiarena/aiarena-client")

# read config file
with open('/home/aiarena/aiarena-client/aiarena-client.json') as config_file:
    config = json.load(config_file)

# print to console and log
def printout(text):
    now = datetime.datetime.now()
    print(colored(now.strftime("%b %d %H:%M:%S"), 'yellow') + " " + colored(config['id'], 'red') + " " + colored(text, 'green'))
    f = open("/home/aiarena/aiarena-client/aiarena-client.log","a+")
    f.write(now.strftime("%b %d %H:%M:%S") + " " + config['id'] + " " + text + "\n")
    f.close()

# Get map file from api by map id
def getmapfile(mapid):
    mapresponse = requests.get('https://ai-arena.net/api/maps/', headers={'Authorization': "Token " + config['token']})
    mapdata = json.loads(mapresponse.text)

    for i in mapdata['results']:
        if i['id'] == mapid:
            mapname = i['name']
            mapurl = i['file']
            r = requests.get(mapurl)
            printout("Downloading map " + mapname)
            with open("/home/aiarena/StarCraftII/maps/" + mapname + ".SC2Map", 'wb') as f:
                f.write(r.content)
            return mapname

# needed for hashlib md5 function
def file_as_bytes(file):
    with file:
        return file.read()

# Get bot file from api by bot id
def getbotfile(botid):
    botresponse = requests.get('https://ai-arena.net/api/bots/', headers={'Authorization': "Token " + config['token']})
    botdata = json.loads(botresponse.text)
    for i in botdata['results']:
        if i['id'] == botid:
            botname = i['name']
            boturl = i['bot_zip']
            botmd5 = i['bot_zip_md5hash']
            r = requests.get(boturl)
            printout("Downloading bot " + botname)
            with open(temppath + botname + ".zip", 'wb') as f:
                f.write(r.content)
            if botmd5 == hashlib.md5(file_as_bytes(open(temppath + botname + ".zip", 'rb'))).hexdigest():
                printout("MD5 hash matches transferred file...")
                printout("Extracting bot " + botname + " to bots/" + botname)
                zip_ref = zipfile.ZipFile(temppath + botname + ".zip", 'r')
                zip_ref.extractall("bots/" + botname)
                zip_ref.close()
                return 1
            else:
                printout("MD5 hash (" + botmd5 + ") doesent match transferred file (" + hashlib.md5(file_as_bytes(open(temppath + botname + ".zip", 'rb'))).hexdigest() + ")")
                cleanup()
                return 0

# Get bot id by name
def getbotid(botname):
    botresponse = requests.get('https://ai-arena.net/api/bots/', headers={'Authorization': "Token " + config['token']})
    botdata = json.loads(botresponse.text)
    for i in botdata['results']:
        if i['name'] == botname:
            return i['id']

# Get bot file from api by bot id
def getbotdata(botid):
    botresponse = requests.get('https://ai-arena.net/api/bots/', headers={'Authorization': "Token " + config['token']})
    botdata = json.loads(botresponse.text)
    for i in botdata['results']:
        if i['id'] == botid:
            botname = i['name']
            botrace = i['plays_race']
            bottype = i['type']

            bot_data = {}

            if botrace == 'P':
                bot_data['Race'] = 'Protoss'
            elif botrace == 'T':
                bot_data['Race'] = 'Terran'
            elif botrace == 'Z':
                bot_data['Race'] = 'Zerg'
            elif botrace == 'R':
                bot_data['Race'] = 'Random'

            bot_data['RootPath'] = "/home/aiarena/aiarena-client/bots/" + botname

            if bottype == 'python':
                bot_data['FileName'] = 'run.py'
                bot_data['Type'] = 'Python'
            elif bottype == 'cppwin32':
                bot_data['FileName'] = botname + ".exe"
                bot_data['Type'] = 'Wine'
            elif bottype == 'cpplinux':
                bot_data['FileName'] = botname
                bot_data['Type'] = 'BinaryCpp'
            elif bottype == 'dotnetcore':
                bot_data['FileName'] = botname + ".dll"
                bot_data['Type'] = 'DotNetCore'
            elif bottype == 'java':
                bot_data['FileName'] = botname + ".jar"
                bot_data['Type'] = 'Java'
            elif bottype == 'nodejs':
                bot_data['FileName'] = "main.js"
                bot_data['Type'] = 'NodeJS'

            return(botname, bot_data)

def getnextmatch():
    global count
    nextmatchresponse = requests.get('https://ai-arena.net/api/matches/next/', headers={'Authorization': "Token " + config['token']})
    nextmatchdata = json.loads(nextmatchresponse.text)

    nextmatchid = nextmatchdata['id']
    printout("Next match: " + str(nextmatchid))

    nextmatchmapid = nextmatchdata['map']
    mapname = getmapfile(nextmatchmapid)

    participantresponse = requests.get("https://ai-arena.net/api/participants/?match=" + str(nextmatchid), headers={'Authorization': "Token " + config['token']})
    participantdata = json.loads(participantresponse.text)

    bot_0 = participantdata['results'][0]['bot']
    if not getbotfile(bot_0):
        cleanup()
        count = count - 1
        return
    bot_1 = participantdata['results'][1]['bot']
    if not getbotfile(bot_1):
        cleanup()
        count = count - 1
        return

    (bot_0_name, bot_0_data) = getbotdata(bot_0)
    (bot_1_name, bot_1_data) = getbotdata(bot_1)

    # Write matchuplist file
    with open('matchuplist', 'w') as f:
        f.write("\"" + str(bot_0_name) + "\"vs\"" + str(bot_1_name) + "\"" + str(mapname) + ".SC2Map")

    # Write LadderBots.json file
    botconfig = {}
    botconfig[bot_0_name] = bot_0_data
    botconfig[bot_1_name] = bot_1_data
    ladderbots = { "Bots": botconfig}
    ladderbots_json = json.dumps(ladderbots, indent=4, sort_keys=True)

    with open('LadderBots.json', 'w') as f:
        f.write(ladderbots_json)

    runmatch()

    while not os.path.exists("/home/aiarena/aiarena-client/results.json"):
        time.sleep(1)

    if os.path.isfile("/home/aiarena/aiarena-client/results.json"):
        printout("Game finished")
        postresult(nextmatchid)

def runmatch():
    printout("Starting Game - Round " + str(count))
    subprocess.Popen(["/home/aiarena/aiarena-client/Sc2LadderServer","-e","/home/aiarena/StarCraftII/Versions/Base70154/SC2_x64"], stdout=DEVNULL, stderr=DEVNULL)

def postresult(matchid):
    global count
    # Parse results.json
    with open('/home/aiarena/aiarena-client/results.json') as results_json_file:
        resultdata = json.load(results_json_file)
        for p in resultdata['Results']:
            winner = p['Winner']
            result = p['Result']
            gametime = p['GameTime']

    if result == 'InitializationError':
        cleanup()
        count = count - 1
        return

    if winner == 'Error':
        cleanup()
        count = count - 1
        return

    # Collect the replayfile
    for file in os.listdir("/home/aiarena/aiarena-client/replays"):
        if file.endswith(".SC2Replay"):
            replayfile = file

    replay_file = {'replay_file': open("/home/aiarena/aiarena-client/replays/" + replayfile, 'rb')}
    payload = {'type': result, 'match': int(matchid), 'winner': getbotid(winner), 'duration': gametime}
    post = requests.post("https://ai-arena.net/api/results/", files=replay_file, data=payload, headers={'Authorization': "Token " + config['token']})

    cleanup()

def cleanup():
    if os.path.isfile("/home/aiarena/aiarena-client/matchuplist"):
        os.remove("/home/aiarena/aiarena-client/matchuplist")
    if os.path.isfile("/home/aiarena/aiarena-client/LadderBots.json"):
        os.remove("/home/aiarena/aiarena-client/LadderBots.json")
    if os.path.isfile("/home/aiarena/aiarena-client/playerids"):
        os.remove("/home/aiarena/aiarena-client/playerids")
    if os.path.isfile("/home/aiarena/aiarena-client/results.json"):
        os.remove("/home/aiarena/aiarena-client/results.json")

    for file in os.listdir("/home/aiarena/aiarena-client/replays"):
        os.remove("/home/aiarena/aiarena-client/replays/" + file)

    for file in os.listdir(temppath):
        os.remove(temppath + file)

    for dir in os.listdir("/home/aiarena/aiarena-client/bots"):
        shutil.rmtree("/home/aiarena/aiarena-client/bots/" + dir)

while count <= config['rounds']:
    count = count + 1
    getnextmatch()

if config['shutdown'] == "true":
    printout("Stopping system")
    f = open("/home/aiarena/aiarena-client/.shutdown","w")
    f.write("Shutdown")
    f.close()