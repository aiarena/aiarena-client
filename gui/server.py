import random
from imutils import build_montages
from datetime import datetime
from multiprocessing import Process
from arenaclient import imagezmq
from flask import Response, request, redirect, jsonify
from flask import Flask
from flask import render_template
import threading
import os
from pathlib import Path
import imutils
import tkinter
from tkinter import filedialog
import cv2
import json
from arenaclient.matches import FileMatchSource
import arenaclient.default_local_config as config
from arenaclient.client import Client
from arenaclient.utl import Utl
from pathlib import Path
import requests
import zipfile
import hashlib
lock = threading.Lock()

# initialize a flask object
app = Flask(__name__)
AI_ARENA_URL = r'https://ai-arena.net:444/'
output_frame = None

class Bot():
    def __init__(self, bot):
        self.bot = bot
        self.type = None
        self.settings = None
 
        self.extract_bot_data()
    @staticmethod
    def find_values(id, json_repr):
        results = []

        def _decode_dict(a_dict):
            try: results.append(a_dict[id])
            except KeyError: pass
            return a_dict

        json.loads(json_repr, object_hook=_decode_dict)  # Return value ignored.
        return results
    
    def download_bot(self):
        self.bot = self.bot.replace(' (AI-Arena)','')
        r = requests.get(
                AI_ARENA_URL+f'api/bots/?format=json&name={self.bot}', headers={"Authorization": "Token " + self.settings['API_token']}
            )
        data = json.loads(r.text)

        self.type = data['results'][0]['type']
        md5_hash = data['results'][0]['bot_zip_md5hash']
        if os.path.isdir(os.path.join(self.settings['bot_directory_location'], self.bot)):
            path = Path(os.path.join(self.settings['bot_directory_location'],'Bot Zip Files'))
            if not path.is_dir():
                path.mkdir()
            if Path(os.path.join(path,self.bot+'.zip')).exists():
                with open(os.path.join(path, self.bot+'.zip'), "rb") as bot_zip:
                    calculated_md5 = hashlib.md5(bot_zip.read()).hexdigest()
                if md5_hash == calculated_md5:
                    print('Do not download')
                    return
        r = requests.get(
            AI_ARENA_URL+f'api/bots/?format=json&name={self.bot}', headers={"Authorization": "Token " + self.settings['API_token']}
        )
        bot_zip = data['results'][0]['bot_zip']
        r = requests.get(bot_zip, headers={"Authorization": "Token " + self.settings['API_token']}, stream=True)
            
        bot_download_path = os.path.join(path, self.bot+ ".zip")
        with open(bot_download_path, "wb") as bot_zip:
            for chunk in r.iter_content(chunk_size=10*1024):
                bot_zip.write(chunk)
            # bot_zip.write(r.content)
    
        # Extract to bot folder
        with zipfile.ZipFile(bot_download_path, "r") as zip_ref:
            zip_ref.extractall(os.path.join(self.settings['bot_directory_location'], self.bot))
            # os.remove(bot_download_path)
    
    def extract_bot_data(self):
        settings = load_settings_from_file()  
        self.settings = settings
        if ' (AI-Arena)' in self.bot:
            self.download_bot()
            return
        

        with open(os.path.join(settings['bot_directory_location'],self.bot,'ladderbots.json')) as f:
            self.type = self.find_values('Type',f.read())[0]

def detect_motion(frame_count):
    global output_frame, lock
    image_hub = imagezmq.ImageHub(open_port='tcp://127.0.0.1:5556', REQ_REP=False)
    image_hub.connect('tcp://127.0.0.1:5557')

    frame_dict = {}
    last_active = {}
    estimated_num_pis = 2
    active_check_period = 10
    active_check_seconds = estimated_num_pis * active_check_period

    m_w = 2
    m_h = 4
    total = 0
    while True:
        (rpiName, frame) = image_hub.recv_image()
        # image_hub.send_reply(b'OK')

        # if rpiName not in last_active.keys():
        # 	print("[INFO] receiving data from {}...".format(rpiName))

        # last_active[rpiName] = datetime.now()

        # frame = imutils.resize(frame, width=800, height=800)
        # frame = cv2.resize(frame, dsize=None, fx=2, fy=2)
        (h, w) = frame.shape[:2]
        frame_dict[rpiName] = frame
        # if total > frame_count:
        montages = build_montages(frame_dict.values(), (w, h), (m_w, m_h))

        # display the montage(s) on the screen
        for (i, montage) in enumerate(montages):
            # with lock:
            output_frame = montage
            
            # break
	# total +=1
	# if (datetime.now() - lastActiveCheck).seconds > ACTIVE_CHECK_SECONDS:
	# 	# loop over all previously active devices
	# 	for (rpiName, ts) in list(lastActive.items()):
	# 		# remove the RPi from the last active and frame
	# 		# dictionaries if the device hasn't been active recently
	# 		if (datetime.now() - ts).seconds > ACTIVE_CHECK_SECONDS:
	# 			print("[INFO] lost connection to {}".format(rpiName))
	# 			lastActive.pop(rpiName)
	# 			frameDict.pop(rpiName)

	# 	# set the last active check time as current time
	# 	lastActiveCheck = datetime.now()

def generate():
	# grab global references to the output frame and lock variables
	global output_frame, lock

	# loop over frames from the output stream
	while True:
		# wait until the lock is acquired
		with lock:
			# check if the output frame is available, otherwise skip
			# the iteration of the loop
			if output_frame is None:
				continue

			# encode the frame in JPEG format
			(flag, encodedImage) = cv2.imencode(".jpg", output_frame)

			# ensure the frame was successfully encoded
			if not flag:
				continue
                # cv2.imshow("Minimap", output_frame)
                # cv2.waitKey(1)
		# yield the output frame in the byte format
		yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' +
			   bytearray(encodedImage) + b'\r\n')

def save_settings_to_file(data):
    data['bot_directory_location']=data.get('bot_directory_location', None)
    data['sc2_directory_location'] = data.get('sc2_directory_location', None)
    data['replay_directory_location'] = data.get('replay_directory_location', None)
    data['max_game_time'] = data.get('max_game_time', 60486)
    data['allow_debug'] = data.get('allow_debug', 'Off')
    data['visualize'] = data.get('visualize', 'Off')
    file_settings = None
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'settings.json')
    if os.path.isfile(path):
        with open(path,'r') as settings:
            try:
                file_settings = json.load(settings)
                for x, y in data.items():
                    if y:
                        file_settings[x]=y                  
                
            except:
                    pass
    data = file_settings if file_settings else data
    with open(path,'w+') as settings:
        print('write')
        json.dump(data,settings)
    
def load_settings_from_file():
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)),'settings.json')
    if os.path.isfile(path):
        with open(path,'r') as settings:
            try:
                data= json.loads(settings.read())
                return data
            except:
                return {}
    else:
        return {}

def load_default_settings():
    pass #TODO: get default values for settings.json if the file doesn't already exist

@app.route("/")
def index():
	return render_template("index.html")

@app.route("/video_feed")
def video_feed():
	# return the response generated along with the specific media
	# type (mime type)
	return Response(generate(),
					mimetype="multipart/x-mixed-replace; boundary=frame")

@app.route("/settings")
def settings():
    return render_template("settings.html")

@app.route('/watch')
def watch():
    return render_template("watch.html")

@app.route('/handle_data', methods=['POST'])
def handle_data():
    data = request.form
    
    save_settings_to_file(data.to_dict())
    return redirect("/")

@app.route('/get_settings', methods=['GET'])
def get_settings():
    return jsonify(load_settings_from_file())


@app.route('/folder_dialog')
def folder_dialog():
    root = tkinter.Tk()
    root.withdraw()
    dirname = filedialog.askdirectory(parent=root,initialdir="/",title='Please select a directory')
    root.destroy()
    return Response(dirname)

@app.route('/get_results',methods=['GET'])
def get_results():
    try:
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'results.json'),'r') as f:
            data= json.loads(f.read())
            return jsonify(data.get('Results',[]))
    except Exception as e:
        return str(e)


def run_local_game(games, data):
    config.ROUNDS_PER_RUN = 1
    config.REALTIME = data.get("Realtime", 'false') == 'true'    
    config.VISUALIZE = data.get("Visualize", 'false') == 'true' 
    config.MATCH_SOURCE_CONFIG = FileMatchSource.FileMatchSourceConfig(		
    matches_file=os.path.join(os.path.dirname(os.path.realpath(__file__)), "matches"),		
    results_file=os.path.join(os.path.dirname(os.path.realpath(__file__)),'results.json'))

    for key in games:
        with open(config.MATCH_SOURCE_CONFIG.MATCHES_FILE, "w+") as f:
            f.write(key + os.linesep)
        ac = Client(config)
        ac.run()

@app.route('/run_games',methods=['POST'])
def run_games():
    games = []
    
    data = request.form.to_dict(flat=False)
    bot1 =data['Bot1[]']
    bot2 =data['Bot2[]']
    chosen_maps = data["Map[]"]
    for maps in chosen_maps:
        if maps == "Random":
            maps = random.choice(get_local_maps())
        for x in bot1:
            x = Bot(x)
            for y in bot2:                
                y=Bot(y)
                game = f'{x.bot},T,{x.type},{y.bot},T,{y.type},{maps}'
                games.append(game)

    proc = Process(target=run_local_game, args=[games,data])
    proc.start()
    return Response("Game Started")

@app.route('/get_bots', methods=['GET'])
def get_bots():
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'settings.json')) as f:
        directory = json.load(f)['bot_directory_location']
    
    if not os.path.isdir(directory):
        return jsonify({"Error":"Please enter a directory"})
    
    if len(os.listdir(directory)) < 1:
        return jsonify({"Error":f"No bots found in {directory}"})
    bot_json = {'Bots':[]}
    for x in os.listdir(directory):
        path = os.path.join(directory,x)
        if os.path.isfile(os.path.join(path,'ladderbots.json')):
            bot_json['Bots'].append(x)

    # return Response(200)
    return jsonify(bot_json)

@app.route('/get_arena_bots', methods=['GET'])
def get_arena_bots():
    data = load_settings_from_file()
    token = data.get('API_token','')
    if  token == '':
        return "No token"
    else:
        r = requests.get(AI_ARENA_URL+r'api/bots/?&format=json&id=&user=&name=&created=&active=&in_match=&current_match=&plays_race=&type=&game_display_id=&bot_zip_updated=&bot_zip_publicly_downloadable=true', headers={"Authorization": "Token " + token})
        return r.text
        

def get_local_maps():
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'settings.json')) as f:
        directory = json.load(f)['sc2_directory_location']
    
    if not os.path.isdir(directory):
        return jsonify({"Error":"Please enter a directory"})
    BASE = Path(directory).expanduser()
           

    if (BASE / "maps").exists():
        MAPS = BASE / "maps"
    else:
        MAPS = BASE / "Maps"
    map_json = {'Bots':[]}
    maps = []
    for mapdir in (p for p in MAPS.iterdir()):
        if mapdir.is_dir():
            for mapfile in (p for p in mapdir.iterdir() if p.is_file()):
                if mapfile.suffix == ".SC2Map":
                    maps.append(mapfile.stem)
        elif mapdir.is_file():
            if mapdir.suffix == ".SC2Map":
                maps.append(mapdir.stem)
    return maps

@app.route('/get_maps', methods=['GET'])
def get_maps():
    return jsonify({'Maps':get_local_maps()})

def run_server(host='0.0.0.0', port=8080):
    # construct the argument parser and parse command line arguments

	# start a thread that will perform motion detection
	t = threading.Thread(target=detect_motion, args=(
		30,))
	t.daemon = True
	t.start()

	# start the flask app
	app.run(host=host, port=port, debug=False,
			threaded=True, use_reloader=False)
# check to see if this is the main thread of execution
if __name__ == '__main__':
    run_server()
	
