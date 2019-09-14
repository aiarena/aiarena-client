import traceback
import stat
import aiohttp
import asyncio
import json
import subprocess
import os
import signal
import traceback
import stat
import platform
import datetime
import time
import sys
import psutil
from termcolor import colored
import socket
import logging
RUN_LOCAL = False
logger = logging.getLogger(__name__)
logger.addHandler(logging.FileHandler('supervisor.log', 'a+'))
logger.setLevel(10)
if not RUN_LOCAL:
    import hashlib
   
    import zipfile
    from pathlib import Path
    import shutil
    import requests
    from requests.exceptions import ConnectionError
    import socket
    
    from utl import *
    # the default config will also import custom config values
    import default_config as config

SYSTEM = platform.system()
HOST = os.getenv('HOST', '127.0.0.1')
PORT = int(os.getenv('PORT', 8765))
if RUN_LOCAL:
    WORKING_DIRECTORY = os.getcwd()
    REPLAY_DIRECTORY = os.path.join(WORKING_DIRECTORY, "Replays/")
    # Try to import config settings
    with open('LadderManager.json', 'r') as lm:
        j_object = json.load(lm)
        PYTHON = j_object['PythonBinary']
        DISABLE_DEBUG = j_object['DisableDebug']
        RESULTS_LOG_FILE = j_object['ResultsLogFile']
        MAX_GAME_TIME = j_object['MaxGameTime']
        REALTIME_MODE =j_object['RealTimeMode']
        BOTS_DIRECTORY = j_object['BaseBotDirectory']

else:
    PYTHON = config.PYTHON
    REPLAY_DIRECTORY = config.REPLAYS_DIRECTORY
    WORKING_DIRECTORY = config.WORKING_DIRECTORY
    MAX_GAME_TIME = 60486
if RUN_LOCAL:
    def printout(text):
        now = datetime.datetime.now()
        infos = [now.strftime("%b %d %H:%M:%S"), text]
        # Maps yellow to the first info, red to the second, green for the text
        colors = ["yellow", "red", "green"]
        colored_infos = " ".join(colored(info, color) for info, color in zip(infos, colors))
        print(colored_infos)
        with open('ladder_manager.stdout', "a+") as f:
            line = " ".join(infos) + "\n"
            f.write(line)

def check_pid(pid):
    try:
        os.kill(pid,0)
    except OSError:
        return False
    else:
        return True

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
            # Chmod 744: rwxr--r--
            os.chmod(f'bots/{botname}/{botname}', stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)

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

def getbotdata(bot=None):
	if not bot:
		botname = "OverReactBot"
		botrace = "T"
		bottype = "python"
		botid = "123"
	else:    
		botname=bot["name"]
		botrace=bot["plays_race"]
		bottype=bot["type"]
		botid=bot["game_display_id"]

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
		"RootPath": os.path.join(WORKING_DIRECTORY, f"bots", botname),
		"FileName": bot_type_map[bottype][0],
		"Type": bot_type_map[bottype][1],
		"botID": botid,
	}
	return botname, bot_data

def get_ladder_bots_data(bot):
    bot_directory = os.path.join(BOTS_DIRECTORY,bot,'ladderbots.json')
    with open(bot_directory,'r') as f:
        j_object = json.load(f)
    return bot, j_object

def getnextmatch(count):
    printout(f'New match started at {time.strftime("%H:%M:%S", time.gmtime(time.time()))}')
    if not RUN_LOCAL:
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
        bot_0_game_display_id = bot_0_data['botID']
        bot_1_game_display_id = bot_1_data['botID']
        
        result = runmatch(count, mapname, bot_0_name, bot_1_name,bot_0_data,bot_1_data,nextmatchid)
        # printout(result)
        postresult(nextmatchdata, result,bot_0_name,bot_1_name)
        return True
    
    else:
        with open('matchupList','r') as ml:
            for i,line in enumerate(ml):
                nextmatchid = i
                Line = line 
                break
        printout(f"Next match: {nextmatchid}")
        mapname = Line.split(" ")[1].replace('\n','').replace('.SC2Map','')
        bot_0 = Line.split('vs')[0].replace("\"","")
        bot_1 = Line.split('vs')[1].split(' ')[0].replace("\"","")
        bot_0_name, bot_0_data = get_ladder_bots_data(bot_0)
        bot_1_name, bot_1_data = get_ladder_bots_data(bot_1)
        # bot_0_game_display_id = bot_0_data['botID']#TODO: Enable opponent_id
        # bot_1_game_display_id = bot_1_data['botID']
        result = runmatch(count, mapname, bot_0_name, bot_1_name,bot_0_data,bot_1_data,nextmatchid)
        post_local_result(bot_0,bot_1,result)
        return True

def postresult(match, lm_result,bot_1_name,bot_2_name):
    if isinstance(lm_result,list):
        for x in lm_result:
            if x.get('Result',None):
                temp_results = x['Result']
                bot_1_name = list(x['Result'].keys())[0]
                bot_2_name = list(x['Result'].keys())[1]
                if temp_results[bot_1_name] == 'Result.Victory':
                    result='Player1Win'
                    # result_json['Winner']=bot_1_name
                
                elif temp_results[bot_1_name] == 'Result.Defeat':
                    result = 'Player2Win'
                    # result_json['Winner']=bot_1
                
                elif temp_results[bot_1_name] == 'Result.Crashed':
                    result = 'Player1Crash'
                    # result_json['Winner']=bot_1
                
                elif temp_results[bot_2_name] == 'Result.Crashed':
                    result = 'Player2Crash'
                    # result_json['Winner']=bot_0
                
                elif temp_results[bot_1_name] =='Result.Tie':
                    result = 'Tie'
                    # result_json['Winner']='Tie'
                
                else:
                    result = 'InitializationError'
                    gametime = 0
                    bot1_avg_step_time =0
                    bot2_avg_step_time=0

                # result_json['Result'] = result
            
            if x.get('GameTime',None):
                gametime = x['GameTime']
                gametime_formatted = x['GameTimeFormatted']
            
            if x.get('AverageFrameTime',None):
                bot1_avg_step_time = (next(iter(x['AverageFrameTime']))).get(bot_1_name,0)
                bot2_avg_step_time = (next(iter(x['AverageFrameTime']))).get(bot_2_name,0)
            
            if x.get('TimeStamp',None):
                time_stamp = x['TimeStamp']
    
    else:
        result = lm_result
        gametime = 0
        bot1_avg_step_time =0
        bot2_avg_step_time=0

    replayfile = ""
    for file in os.listdir(REPLAY_DIRECTORY):
        if file.endswith(".SC2Replay"):
            replayfile = file
            break
    replay_file_path = os.path.join(REPLAY_DIRECTORY, replayfile)
    if config.RUN_REPLAY_CHECK:
        os.system("perl " + os.path.join(config.LOCAL_PATH,
                                         "replaycheck.pl") + " " + replay_file_path)

    bot1_data_folder = os.path.join(
        config.WORKING_DIRECTORY, "bots", bot_1_name, "data")
    bot2_data_folder = os.path.join(
        config.WORKING_DIRECTORY, "bots", bot_2_name, "data")
    bot1_error_log = os.path.join(bot1_data_folder, "stderr.log")
    bot1_error_log_tmp = os.path.join(
        config.TEMP_PATH, bot_1_name + "-error.log")
    if os.path.isfile(bot1_error_log):
        shutil.move(bot1_error_log, bot1_error_log_tmp)
    else:
        Path(bot1_error_log_tmp).touch()

    bot2_error_log = os.path.join(bot2_data_folder, "stderr.log")
    bot2_error_log_tmp = os.path.join(
        config.TEMP_PATH, bot_2_name + "-error.log")
    if os.path.isfile(bot2_error_log):
        shutil.move(bot2_error_log, bot2_error_log_tmp)
    else:
        Path(bot2_error_log_tmp).touch()

    zip_file = zipfile.ZipFile(os.path.join(
        config.TEMP_PATH, bot_1_name + "-error.zip"), 'w')
    zip_file.write(os.path.join(config.TEMP_PATH, bot_1_name +
                                "-error.log"), compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()

    zip_file = zipfile.ZipFile(os.path.join(
        config.TEMP_PATH, bot_2_name + "-error.zip"), 'w')
    zip_file.write(os.path.join(config.TEMP_PATH, bot_2_name +
                                "-error.log"), compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()


    # sc2ladderserver logs
    sc2ladderserver_stdout_log_tmp = os.path.join(
        config.TEMP_PATH, "sc2ladderserver_stdout.log")
    sc2ladderserver_stderr_log_tmp = os.path.join(
        config.TEMP_PATH, "sc2ladderserver_stderr.log")
    sc2ladderserver_log_zip = os.path.join(
        config.TEMP_PATH, "sc2ladderserver_log.zip")

    if os.path.isfile(config.SC2LADDERSERVER_STDOUT_FILE):
        shutil.move(config.SC2LADDERSERVER_STDOUT_FILE,
                    sc2ladderserver_stdout_log_tmp)
    else:
        Path(sc2ladderserver_stdout_log_tmp).touch()

    if os.path.isfile(config.SC2LADDERSERVER_STDERR_FILE):
        shutil.move(config.SC2LADDERSERVER_STDERR_FILE,
                    sc2ladderserver_stderr_log_tmp)
    else:
        Path(sc2ladderserver_stderr_log_tmp).touch()

    zip_file = zipfile.ZipFile(sc2ladderserver_log_zip, 'w')
    zip_file.write(sc2ladderserver_stdout_log_tmp,
                   compress_type=zipfile.ZIP_DEFLATED)
    zip_file.write(sc2ladderserver_stderr_log_tmp,
                   compress_type=zipfile.ZIP_DEFLATED)
    zip_file.close()

    # Create downloable data archives
    if not os.path.isdir(bot1_data_folder):
        os.mkdir(bot1_data_folder)
    shutil.make_archive(os.path.join(
        config.TEMP_PATH, bot_1_name + "-data"), "zip", bot1_data_folder)
    if not os.path.isdir(bot2_data_folder):
        os.mkdir(bot2_data_folder)
    shutil.make_archive(os.path.join(
        config.TEMP_PATH, bot_2_name + "-data"), "zip", bot2_data_folder)

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

        payload = {"type": result, "match": int(
            match["id"]), "game_steps": gametime}

        if bot1_avg_step_time is not None:
            payload["bot1_avg_step_time"] = bot1_avg_step_time
        if bot2_avg_step_time is not None:
            payload["bot2_avg_step_time"] = bot2_avg_step_time

        if config.DEBUG_MODE:
            printout(json.dumps(payload))

        post = requests.post(config.API_RESULTS_URL, files=file_list, data=payload,
                             headers={"Authorization": "Token " + config.API_TOKEN})
        if post is None:
            printout("ERROR: Result submission failed. 'post' was None.")
        elif post.status_code >= 400:  # todo: retry?
            printout(
                f"ERROR: Result submission failed. Status code: {post.status_code}.")
        else:
            printout(result + " - Result transferred")
    except ConnectionError as ce:
        printout(f"ERROR: Result submission failed. Connection to website failed.")

def post_local_result(bot_0,bot_1,lm_result):
    result_json = {
        "Bot1":bot_0,
        "Bot2":bot_1,
        "Winner":None,
        "Map":None,
        "Result":None,
        "GameTime":None,
        "GameTimeFormatted":None,
        "TimeStamp":None,
        "Bot1AvgFrame": 0,
        "Bot2AvgFrame": 0
        }
    for x in lm_result:
        if x.get('Result',None):
            temp_results = x['Result']
            if temp_results[bot_0] == 'Result.Victory':
                result='Player1Win'
                result_json['Winner']=bot_0
            
            elif temp_results[bot_0] == 'Result.Defeat':
                result = 'Player2Win'
                result_json['Winner']=bot_1
            
            elif temp_results[bot_0] == 'Result.Crashed':
                result = 'Player1Crash'
                result_json['Winner']=bot_1
            
            elif temp_results[bot_1] == 'Result.Crashed':
                result = 'Player2Crash'
                result_json['Winner']=bot_0
            
            elif temp_results[bot_0] =='Result.Tie':
                result = 'Tie'
                result_json['Winner']='Tie'
            
            else:
                result = 'InitializationError'

            result_json['Result'] = result
        
        if x.get('GameTime',None):
            result_json['GameTime'] = x['GameTime']
            result_json['GameTimeFormatted'] = x['GameTimeFormatted']
        
        if x.get('AverageFrameTime',None):
            result_json['Bot1AvgFrame'] = (next(iter(x['AverageFrameTime']))).get(bot_0,0) *1000#Convert to ms
            result_json['Bot2AvgFrame'] = (next(iter(x['AverageFrameTime']))).get(bot_1,0)*1000#Convert to ms
        
        if x.get('TimeStamp',None):
            result_json['TimeStamp'] = x['TimeStamp']

    # if os.path.isfile(RESULTS_LOG_FILE):#TODO: Fix the appending of results
    #     f=open(RESULTS_LOG_FILE, 'r')
    #     if len(f.readlines()) > 0:
    #         f.close()
    #         with open(RESULTS_LOG_FILE, 'w+') as results_log:
    #             j_object = json.load(results_log) 
    #             if j_object.get('Results',None):
    #                 logger.debug('append')
    #                 j_object['Results'].append(result_json)
                
    #             else:
    #                 logger.debug('Overwrite')
    #                 j_object['Results'] =[result_json]
                
    #             results_log.write(json.dumps(j_object, indent=4))
    # else:
        with open(RESULTS_LOG_FILE,'w') as results_log:
            j_object = dict({'Results':[result_json]})
            results_log.write(json.dumps(j_object, indent=4))

def cleanup():
    # Files to remove
    files = [
        config.SC2LADDERSERVER_PID_FILE,
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
    folders = [REPLAY_DIRECTORY, config.TEMP_PATH]
    for folder in folders:
        for file in os.listdir(folder):
            file_path = os.path.join(folder, file)
            os.remove(file_path)

    # Remove entire subfolders
    bots_dir = os.path.join(config.WORKING_DIRECTORY, "bots")
    for dir in os.listdir(bots_dir):
        shutil.rmtree(os.path.join(bots_dir, dir))
    logger.debug(f'Killing current server')
    kill_current_server()

def start_bot(bot_data, opponent_id):
    bot_data = bot_data['Bots'] if RUN_LOCAL else bot_data
    bot_name = next(iter(bot_data))
    bot_data = bot_data[bot_name] if RUN_LOCAL else bot_data
    bot_path = os.path.join(BOTS_DIRECTORY,bot_name) if RUN_LOCAL else bot_data['RootPath']#hotfix
    bot_file = bot_data['FileName']
    bot_type = bot_data['Type']
    cmd_line = [bot_file, "--GamePort", str(PORT), "--StartPort", str(
        PORT), "--LadderServer", HOST, "--OpponentId", str(opponent_id)]
    if bot_type.lower() == "python":
        cmd_line.insert(0, PYTHON)
    elif bot_type.lower() == "wine":
        cmd_line.insert(0, "wine")
    elif bot_type.lower() == "mono":
        cmd_line.insert(0, "mono")
    elif bot_type.lower() == "dotnetcore":
        cmd_line.insert(0, "dotnet")
    elif bot_type.lower() == "commandcenter":
        raise
    elif bot_type.lower() == "binarycpp":
        cmd_line.insert(0, os.path.join(bot_path, bot_file))
    elif bot_type.lower() == "java":
        cmd_line.insert(0, "java")
        cmd_line.insert(1, "-jar")
    elif bot_type.lower() == "nodejs":
        raise
    
    try:
        os.stat(os.path.join(bot_path, "data"))
    except:
        os.mkdir(os.path.join(bot_path, "data"))
    try:
        os.stat(REPLAY_DIRECTORY)
    except:
        os.mkdir(REPLAY_DIRECTORY)
    try:
        if SYSTEM == "Linux":
            with open(os.path.join(bot_path, "data", "stderr.log"), "w+") as out:
                process = subprocess.Popen(
                    ' '.join(cmd_line),
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    # creationflags=subprocess.CREATE_NEW_CONSOLE,
                    cwd=(str(bot_path))
                    ,shell=True
                    ,preexec_fn=os.setpgrp

                )
            if process.errors:
                logger.debug("Error: "+process.errors)
            return process
        else:
            with open(os.path.join(bot_path, "data", "stderr.log"), "w+") as out:
                process = subprocess.Popen(
                    ' '.join(cmd_line),
                    stdout=out,
                    stderr=subprocess.STDOUT,
                    # creationflags=subprocess.CREATE_NEW_CONSOLE,
                    cwd=(str(bot_path))
                    ,shell=True
                    ,creationflags=subprocess.CREATE_NEW_PROCESS_GROUP

                )
            if process.errors:
                logger.debug("Error: "+process.errors)
            return process
    except Exception as e:
        printout(e)
        sys.exit(0)

def pid_cleanup(pids):
    for pid in pids:
        logger.debug("Killing: "+ str(pid))
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception as e:
            logger.debug("Already closed: "+ str(pid))

def move_pid(pid):
    if pid !=0:
        return
    else:
        for i in range(0,5):
            try:
                os.setpgid(pid, 0)
                return
            except OSError:
                if os.getpgid(pid) == 0:
                    return
                time.sleep(0.25) # sleep for retry

async def main(mapname, bot_0_name, max_game_time, bot_1_name,bot_0_data,bot_1_data,nextmatchid):
    result = []
    session = aiohttp.ClientSession()
    ws = await session.ws_connect(f'http://{HOST}:{str(PORT)}/sc2api', headers=dict({'Supervisor': 'true'}))
    json_config = {"Config":{'Map': mapname, 'MaxGameTime': max_game_time,
                   'Player1': bot_0_name, 'Player2': bot_1_name, 'ReplayPath': REPLAY_DIRECTORY, "MatchID": nextmatchid, 'DisableDebug': "False"}}

    await ws.send_str(json.dumps(json_config))
    bot_counter =0
    while True:
        msg = await ws.receive()
        if msg.type == aiohttp.WSMsgType.CLOSED:
            result.append({'Result':{bot_0_name:'InitializationError'}})
            await session.close()
            break
        msg = msg.json()
        if msg.get("Status", None) == "Connected":
            logger.debug(f"Starting bots...")
            bot1_process = start_bot(bot_0_data, opponent_id=bot_1_data.get('botID',123))
            while not ((await ws.receive()).json()).get("Bot",None) and bot_counter < 300:
                bot_counter+=1
                await asyncio.sleep(0.1)
            bot2_process = start_bot(bot_1_data, opponent_id=bot_0_data.get('botID',321))
            bot_counter =0
            while not ((await ws.receive()).json()).get("Bot",None) and bot_counter < 300:
                bot_counter+=1
                await asyncio.sleep(0.1)
            logger.debug(f'Changing PGID')
            for x in [bot1_process.pid,bot2_process.pid]:
                move_pid(x)

            logger.debug(f'checking if bot is okay')

            if bot1_process.poll():
                logger.debug(f"Bot1 crash")
                result.append({'Result':{bot_0_name:'InitializationError'}})
                await session.close()
                break
                
            else:
                await ws.send_str(json.dumps({'Bot1':True}))
            
            if bot2_process.poll():
                logger.debug(f"Bot2 crash")
                result.append({'Result':{bot_1_name:'InitializationError'}})
                await session.close()
                break
                
                
            else:
                await ws.send_str(json.dumps({'Bot2':True}))

        if msg.get("PID", None):
            pid_cleanup([bot1_process.pid, bot2_process.pid])  # Terminate bots first
            pid_cleanup(msg['PID'])  # Terminate SC2 processes

        if msg.get("Result", None):
            result.append(msg)

        if msg.get("GameTime", None):
            result.append(msg)

        if msg.get('AverageFrameTime', None):
            result.append(msg)

        if msg.get("Error", None):
            await session.close()
            break

        if msg.get("StillAlive",None):
            if bot1_process.poll():
                printout("Bot1 Init Error")
                await session.close()
            # if not check_pid(bot1_process.pid) and not len(result) >0:
                result.append({'Result':{bot_0_name:'InitializationError'}})
            if bot2_process.poll():
                printout("Bot2 Init Error")
                await session.close()
            # if not check_pid(bot2_process.pid) and not len(result) >0:
                result.append({'Result':{bot_1_name:'InitializationError'}})

        if msg.get("Status", None) == "Complete":
            result.append(dict({'TimeStamp':datetime.datetime.utcnow().strftime("%d-%m-%Y %H-%M-%SUTC")}))
            await session.close()
            break
    if not result:
        result.append({'Result':{'InitializationError'}})
    return result

def kill_current_server():

    try:
        if SYSTEM =="Linux":
            printout("Killing SC2")
            os.system('pkill -f SC2_x64')
            os.system('lsof -ti tcp:8765 | xargs kill')
        for proc in psutil.process_iter():
            for conns in proc.connections(kind='inet'):
                if conns.laddr.port == PORT:
                    proc.send_signal(signal.SIGTERM)
            if proc.name() == 'SC2_x64.exe':
                proc.send_signal(signal.SIGTERM)

	       
    except:
        pass
def runmatch(count,mapname,bot_0_name, bot_1_name,bot_0_data,bot_1_data,nextmatchid):
    printout(f"Starting game - Round {count}")
    kill_current_server()
    proxy = subprocess.Popen( PYTHON+ ' Proxy.py',
                            cwd=WORKING_DIRECTORY, shell=True)

    
    while True:
        time.sleep(1)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((HOST,PORT))
        if result == 0:
            break

    loop = asyncio.get_event_loop()
    

    result = loop.run_until_complete(asyncio.wait_for(main(mapname,bot_0_name,MAX_GAME_TIME, bot_1_name,bot_0_data,bot_1_data,nextmatchid),9000))

    try:
        os.kill(proxy.pid, signal.SIGTERM)
    except Exception as e:
        logger.debug(str(e))
    return result

try:
    printout(f'Arena Client started at {time.strftime("%H:%M:%S", time.gmtime(time.time()))}')
    os.makedirs(REPLAY_DIRECTORY, exist_ok=True)
    if not RUN_LOCAL:
        os.makedirs(config.TEMP_PATH, exist_ok=True)
        os.makedirs(os.path.join(config.WORKING_DIRECTORY, "bots"), exist_ok=True)
    
    os.chdir(WORKING_DIRECTORY)
    count = 0
    if RUN_LOCAL:
        try:
            with open('matchupList','r') as ml:
                ROUNDS_PER_RUN = len(ml.readlines())
        except FileNotFoundError:
            f= open('matchupList','w+')
            ROUNDS_PER_RUN=0
            f.close()
    else:
        ROUNDS_PER_RUN = config.ROUNDS_PER_RUN

    while count < ROUNDS_PER_RUN:
        if not RUN_LOCAL:
            cleanup()
        if getnextmatch(count):
            count += 1

        # if RUN_LOCAL:
        #     with open('matchupList','r+') as ml:  
        #         head, tail = ml.read().split('\n', 1)
        #         ml.write(tail)

except Exception as e:
    printout(f"arena-client encountered an uncaught exception: {e} Exiting...")
    if not RUN_LOCAL:
        with open(os.path.join(config.LOCAL_PATH, ".shutdown"), "w") as f:
                f.write("Shutdown")
    traceback.print_exc()
finally:
    try:
        kill_current_server()
        cleanup()  # be polite and try to cleanup
    except:
        pass
if not RUN_LOCAL:
    try:
        if config.SHUT_DOWN_AFTER_RUN:
            printout("Stopping system")
            with open(os.path.join(config.LOCAL_PATH, ".shutdown"), "w") as f:
                f.write("Shutdown")
    except:
        printout("ERROR: Failed to shutdown.")