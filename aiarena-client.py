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


# needed for hashlib md5 function
def file_as_bytes(file):
    with file:
        return file.read()

# Get bot file from api by bot id
def getbotfile(bot):
    botname = bot['name']
    boturl = bot['bot_zip']
    botmd5 = bot['bot_zip_md5hash']
    printout("Downloading bot " + botname)
    botdataurl = bot['bot_data']
    botdatamd5 = bot['bot_data_md5hash']
    r = requests.get(boturl)
    with open(temppath + botname + ".zip", 'wb') as f:
        f.write(r.content)
    if botmd5 == hashlib.md5(file_as_bytes(open(temppath + botname + ".zip", 'rb'))).hexdigest():
        printout("MD5 hash matches transferred file...")
        printout("Extracting bot " + botname + " to bots/" + botname)
        zip_ref = zipfile.ZipFile(temppath + botname + ".zip", 'r')
        zip_ref.extractall("bots/" + botname)
        zip_ref.close()
        if getbotdatafile(bot):
            return 1
    else:
        printout("MD5 hash (" + botmd5 + ") doesent match transferred file (" + hashlib.md5(file_as_bytes(open(temppath + botname + ".zip", 'rb'))).hexdigest() + ")")
        cleanup()
        return 0


# Get bot data
def getbotdatafile(bot):
    botname = bot['name']
    if bot['bot_data'] == None:
        return 1

    botdataurl = bot['bot_data']
    botdatamd5 = bot['bot_data_md5hash']
    printout("Downloading bot data for " + botname)
    r = requests.get(botdataurl)
    with open(temppath + botname + "-data.zip", 'wb') as f:
        f.write(r.content)
    if botdatamd5 == hashlib.md5(file_as_bytes(open(temppath + botname + "-data.zip", 'rb'))).hexdigest():
        printout("MD5 hash matches transferred file...")
        printout("Extracting data for " + botname + " to bots/" + botname + "/data")
        zip_ref = zipfile.ZipFile(temppath + botname + "-data.zip", 'r')
        zip_ref.extractall("bots/" + botname + "/data")
        zip_ref.close()
        return 1
    else:
        printout("MD5 hash (" + botdatamd5 + ") doesent match transferred file (" + hashlib.md5(file_as_bytes(open(temppath + botname + "-data.zip", 'rb'))).hexdigest() + ")")
        cleanup()
        return 0


# Get bot file
def getbotdata(bot):
    botname = bot['name']
    botrace = bot['plays_race']
    bottype = bot['type']

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
    nextmatchresponse = requests.post('https://ai-arena.net/api/arenaclient/matches/', headers={'Authorization': "Token " + config['token']})
    nextmatchdata = json.loads(nextmatchresponse.text)

    if not "id" in nextmatchdata:
        printout('No games available - sleeping')
        time.sleep(30)
        cleanup()
        count = count - 1
        return

    nextmatchid = nextmatchdata['id']
    printout("Next match: " + str(nextmatchid))

    mapname = nextmatchdata['map']['name']
    mapurl = nextmatchdata['map']['file']
    r = requests.get(mapurl)
    printout("Downloading map " + mapname)
    with open("/home/aiarena/StarCraftII/maps/" + mapname + ".SC2Map", 'wb') as f:
        f.write(r.content)

    bot_0 = nextmatchdata['bot1']
    if not getbotfile(bot_0):
        cleanup()
        count = count - 1
        return
    bot_1 = nextmatchdata['bot2']
    if not getbotfile(bot_1):
        cleanup()
        count = count - 1
        return

    (bot_0_name, bot_0_data) = getbotdata(bot_0)
    (bot_1_name, bot_1_data) = getbotdata(bot_1)

    # Write matchuplist file
    with open('matchuplist', 'w') as f:
        f.write("\"" + str(bot_0['name']) + "\"vs\"" + str(bot_1['name']) + "\"" + str(mapname) + ".SC2Map")

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
        postresult(nextmatchdata)

def runmatch():
    printout("Starting Game - Round " + str(count))
    subprocess.Popen(["/home/aiarena/aiarena-client/Sc2LadderServer","-e","/home/aiarena/StarCraftII/Versions/Base70154/SC2_x64"], stdout=DEVNULL, stderr=DEVNULL)

def postresult(match):
    global count
    # Parse results.json
    with open('/home/aiarena/aiarena-client/results.json') as results_json_file:
        resultdata = json.load(results_json_file)
        for p in resultdata['Results']:
            result = p['Result']
            gametime = p['GameTime']

    # Collect the replayfile
    replayfile = ''
    for file in os.listdir("/home/aiarena/aiarena-client/replays"):
        if file.endswith(".SC2Replay"):
            replayfile = file

    if not os.path.isdir("/home/aiarena/aiarena-client/bots/" + match['bot1']['name'] + "/data"):
        os.mkdir("/home/aiarena/aiarena-client/bots/" + match['bot1']['name'] + "/data")
    shutil.make_archive(temppath + match['bot1']['name'] + "-data", 'zip', "/home/aiarena/aiarena-client/bots/" + match['bot1']['name'] + "/data")
    if not os.path.isdir("/home/aiarena/aiarena-client/bots/" + match['bot2']['name'] + "/data"):
        os.mkdir("/home/aiarena/aiarena-client/bots/" + match['bot2']['name'] + "/data")
    shutil.make_archive(temppath + match['bot2']['name'] + "-data", 'zip', "/home/aiarena/aiarena-client/bots/" + match['bot2']['name'] + "/data")

    if os.path.isfile("/home/aiarena/aiarena-client/replays/" + replayfile):
        file_list = {
            'replay_file': open("/home/aiarena/aiarena-client/replays/" + replayfile, 'rb'),
            'bot1_data': open(temppath + match['bot1']['name'] + "-data.zip", 'rb'),
            'bot2_data': open(temppath + match['bot2']['name'] + "-data.zip", 'rb')
        }
        payload = {'type': result, 'match': int(match['id']), 'duration': gametime}
        post = requests.post("https://ai-arena.net/api/arenaclient/results/", files=file_list, data=payload, headers={'Authorization': "Token " + config['token']})
        printout(result + " - Result transferred")
    else:
        payload = {'type': result, 'match': int(match['id']), 'duration': gametime}
        post = requests.post("https://ai-arena.net/api/arenaclient/results/", data=payload, headers={'Authorization': "Token " + config['token']})
        printout(result + " - Result transferred")


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
    cleanup()
    getnextmatch()

if config['shutdown'] == "true":
    printout("Stopping system")
    f = open("/home/aiarena/aiarena-client/.shutdown","w")
    f.write("Shutdown")
    f.close()