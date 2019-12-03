import random
from aiohttp import web, ClientSession
from aiohttp_jinja2 import render_template
import os
import json
from arenaclient.matches import FileMatchSource
import arenaclient.default_local_config as config
from arenaclient.client import Client
from pathlib import Path
from platform import system
import requests
import zipfile
import hashlib
import asyncio

AI_ARENA_URL = r'https://ai-arena.net/'
output_frame = None


class Bot:
    def __init__(self, bot):
        self.name = bot
        self.type = None
        self.settings = None

        self.extract_bot_data()

    @staticmethod
    def find_values(dict_id, json_repr):
        results = []

        def _decode_dict(a_dict):
            try:
                results.append(a_dict[dict_id])
            except KeyError:
                pass
            return a_dict

        json.loads(json_repr, object_hook=_decode_dict)  # Return value ignored.
        return results

    def download_bot(self):
        self.name = self.name.replace(' (AI-Arena)', '')
        r = requests.get(
            AI_ARENA_URL + f'api/bots/?format=json&name={self.name}',
            headers={"Authorization": "Token " + self.settings['API_token']}
        )
        data = json.loads(r.text)

        self.type = data['results'][0]['type']
        md5_hash = data['results'][0]['bot_zip_md5hash']
        path = Path(os.path.join(self.settings['bot_directory_location'], 'Bot Zip Files'))
        if not path.is_dir():
            path.mkdir()

        if os.path.isdir(os.path.join(self.settings['bot_directory_location'], self.name)):
            if not path.is_dir():
                path.mkdir()
            if Path(os.path.join(path, self.name + '.zip')).exists():
                with open(os.path.join(path, self.name + '.zip'), "rb") as bot_zip:
                    calculated_md5 = hashlib.md5(bot_zip.read()).hexdigest()
                if md5_hash == calculated_md5:
                    print('Do not download')
                    return
        bot_zip = data['results'][0]['bot_zip']
        r = requests.get(bot_zip, headers={"Authorization": "Token " + self.settings['API_token']}, stream=True)

        bot_download_path = os.path.join(path, self.name + ".zip")
        with open(bot_download_path, "wb") as bot_zip:
            for chunk in r.iter_content(chunk_size=10 * 1024):
                bot_zip.write(chunk)
            # bot_zip.write(r.content)

        # Extract to bot folder
        with zipfile.ZipFile(bot_download_path, "r") as zip_ref:
            zip_ref.extractall(os.path.join(self.settings['bot_directory_location'], self.name))
            # os.remove(bot_download_path)

    def extract_bot_data(self):
        settings_file = load_settings_from_file()
        self.settings = convert_wsl_paths(settings_file)
        if ' (AI-Arena)' in self.name:
            self.download_bot()
            return

        with open(os.path.join(self.settings['bot_directory_location'], self.name, 'ladderbots.json')) as f:
            self.type = self.find_values('Type', f.read())[0]


def save_settings_to_file(data):
    data['bot_directory_location'] = data.get('bot_directory_location', None)
    data['sc2_directory_location'] = data.get('sc2_directory_location', None)
    data['replay_directory_location'] = data.get('replay_directory_location', None)
    data['max_game_time'] = data.get('max_game_time', 60486)
    data['allow_debug'] = data.get('allow_debug', 'Off')
    data['visualize'] = data.get('visualize', 'Off')
    file_settings = None
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings.json')
    if os.path.isfile(path):
        with open(path, 'r') as settings_file:
            try:
                file_settings = json.load(settings_file)
                for x, y in data.items():
                    if y:
                        file_settings[x] = y

            except:
                pass
    data = file_settings if file_settings else data
    with open(path, 'w+') as settings_file:
        print('write')
        json.dump(data, settings_file)


def load_settings_from_file():
    path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings.json')
    if os.path.isfile(path):
        with open(path, 'r') as settings_file:
            try:
                data = json.loads(settings_file.read())
                return data
            except:
                return {}
    else:
        return {}


def load_default_settings():
    pass  # TODO: get default values for settings.json if the file doesn't already exist

# View functions


async def index(request):
    context = {}
    return render_template("index.html", request, context)


async def settings(request):
    context = {}
    return render_template("settings.html", request, context)


async def watch(request):
    context = {}
    return render_template("watch.html", request, context)


async def clear_results(request):
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'results.json'), 'w') as f:
        data = json.loads('{}')
        data['Results'] = []
        f.write(json.dumps(data))
    return web.Response(text="OK")


async def handle_data(request):
    data = await request.post()
    settings_data = {}
    for key in data:
        settings_data[key] = data.getone(key)

    save_settings_to_file(settings_data)
    location = request.app.router['index'].url_for()
    raise web.HTTPFound(location=location)


def convert_wsl_paths(json_data):
    json_data_modified = {}
    
    if system() == "Windows":
        
        for x, y in json_data.items():
            replaced_string = y.replace('/mnt/c', 'C:').replace('/mnt/d', 'D:')
            json_data_modified[x] = replaced_string
    
    if system() == "Linux":
        
        for x, y in json_data.items():
            replaced_string = y.replace('C:', '/mnt/c').replace('D:', '/mnt/d')
            json_data_modified[x] = replaced_string
    return json_data_modified


async def get_settings(request):
    return web.json_response(convert_wsl_paths(load_settings_from_file()))


async def get_results(request):
    try:
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'results.json'), 'r') as f:
            data = json.loads(f.read())
            return web.json_response(data.get('Results', []))
    except Exception as e:
        return str(e)

class GameRunner:
    def __init__(self):
        self.game_running = False
    
    async def run_local_game(self, games, data):
        if system() == 'Windows':
            config.PYTHON = 'python'
        config.BOTS_DIRECTORY = convert_wsl_paths(load_settings_from_file())['bot_directory_location']
        config.ROUNDS_PER_RUN = 1
        config.REALTIME = data.get("Realtime", False)
        config.VISUALIZE = data.get("Visualize", False)
        config.MATCH_SOURCE_CONFIG = FileMatchSource.FileMatchSourceConfig(
            matches_file=os.path.join(os.path.dirname(os.path.realpath(__file__)), "matches"),
            results_file=os.path.join(os.path.dirname(os.path.realpath(__file__)), 'results.json'))
        self.game_running = True
        for key in games:
            with open(config.MATCH_SOURCE_CONFIG.MATCHES_FILE, "w+") as f:
                f.write(key + os.linesep)
            ac = Client(config)
            await ac.run()
        self.game_running = False


    async def run_games(self, request):
        games = []
        if self.game_running:
            return web.Response(text="Game already running!")

        data = await request.post()
        game_data = {}

        bot1_list = data.getall('Bot1[]')
        bot2_list = data.getall('Bot2[]')
        chosen_maps = data.getall("Map[]")
        iterations = int(data['Iterations'][0])

        for _ in range(iterations):
            for maps in chosen_maps:
                if maps == "Random":
                    maps = random.choice(get_local_maps())
                for bot1 in bot1_list:
                    bot1 = Bot(bot1)
                    for bot2 in bot2_list:
                        bot2 = Bot(bot2)
                        game = f'{bot1.name},T,{bot1.type},{bot2.name},T,{bot2.type},{maps}'
                        games.append(game)
        game_data['Visualize'] = data.get("Visualize", "false") == "true"
        game_data['Realtime'] = data.get('Realtime', 'false') == 'true'

        asyncio.create_task(self.run_local_game(games, game_data))

        if len(games) == 1:
            return web.Response(text="Game started")
        else:
            return web.Response(text="Games started")


async def get_bots(request):
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings.json')) as f:
        directory = convert_wsl_paths(json.load(f))['bot_directory_location']

    if not os.path.isdir(directory):
        return web.json_response({"Error": "Please enter a directory"})

    if len(os.listdir(directory)) < 1:
        return web.json_response({"Error": f"No bots found in {directory}"})
    bot_json = {'Bots': []}
    for x in os.listdir(directory):
        path = os.path.join(directory, x)
        if os.path.isfile(os.path.join(path, 'ladderbots.json')):
            bot_json['Bots'].append(x)

    return web.json_response(bot_json)


async def get_arena_bots(request):
    r = web.Response()
    data = load_settings_from_file()
    token = data.get('API_token', '')
    if token == '':
        return "No token"
    else:
        async with ClientSession() as session:
            async with session.get(AI_ARENA_URL + r'api/bots/?&format=json&bot_zip_publicly_downloadable=true',
                                   headers={"Authorization": "Token " + token}) as resp:
                r.body = await resp.text()

        return r


def get_local_maps():
    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'settings.json')) as f:
        directory = convert_wsl_paths(json.load(f))['sc2_directory_location']

    if not os.path.isdir(directory):
        return web.json_response({"Error": "Please enter a directory"})
    base_dir = Path(directory).expanduser()

    if (base_dir / "maps").exists():
        maps_dir = base_dir / "maps"
    else:
        maps_dir = base_dir / "Maps"
    maps = []
    for mapdir in (p for p in maps_dir.iterdir()):
        if mapdir.is_dir():
            for mapfile in (p for p in mapdir.iterdir() if p.is_file()):
                if mapfile.suffix == ".SC2Map" and mapfile.stem not in maps:
                    maps.append(mapfile.stem)
        elif mapdir.is_file():
            if mapdir.suffix == ".SC2Map" and mapdir.stem not in maps:
                maps.append(mapdir.stem)
    return sorted(maps)


async def get_maps(request):
    return web.json_response({'Maps': get_local_maps()})
