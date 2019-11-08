from imutils import build_montages
from datetime import datetime
from multiprocessing import Process
import imagezmq
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

import arenaclient.default_local_config as config
from arenaclient.client import Client
from arenaclient.utl import Utl

lock = threading.Lock()

# initialize a flask object
app = Flask(__name__)

output_frame = None

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
    m_h = 1
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
            with lock:
                output_frame = montage
            break
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

		# yield the output frame in the byte format
		yield (b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' +
			   bytearray(encodedImage) + b'\r\n')

def save_settings_to_file(data):
    data['bot_directory_location']=data.get('bot_directory_location', None)
    data['sc2_directory_location'] = data.get('sc2_directory_location', None)
    data['replay_directory_location'] = data.get('replay_directory_location', None)
    data['max_game_time'] = data.get('max_game_time', 60486)
    data['allow_debug'] = data.get('allow_debug', 'Off')
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
    data['bot_directory_location']=data.get('bot_directory_location', None)
    data['sc2_directory_location'] = data.get('sc2_directory_location', None)
    data['replay_directory_location'] = data.get('replay_directory_location', None)
    data['max_game_time'] = data.get('max_game_time', 60486)
    data['allow_debug'] = data.get('allow_debug', 'Off')
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
        json.dump(data,settings)

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

def run_local_game(games):
    config.ROUNDS_PER_RUN = 1
    config.REALTIME = True
    for key in games:
        with open(config.MATCH_SOURCE_CONFIG.MATCHES_FILE, "w+") as f:
            f.write(key + os.linesep)
        ac = Client(config)
        ac.run()

@app.route('/run_games',methods=['POST'])
def run_games():
    games = ['loser_bot,T,python,loser_bot,T,python,AutomatonLE']
    proc = Process(target=run_local_game, args=[games])
    proc.start()
    return redirect("/")

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

# check to see if this is the main thread of execution
if __name__ == '__main__':
	# construct the argument parser and parse command line arguments

	# start a thread that will perform motion detection
	t = threading.Thread(target=detect_motion, args=(
		30,))
	t.daemon = True
	t.start()

	# start the flask app
	app.run(host='0.0.0.0', port=8000, debug=False,
			threaded=True, use_reloader=False)
