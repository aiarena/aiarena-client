import subprocess
import json
import default_config as config
from utl import Utl

with open("LadderManager.json", "r") as lm:
    j_object = json.load(lm)
    PYTHON = j_object["PythonBinary"]
    # DISABLE_DEBUG = j_object["DisableDebug"]
    RESULTS_LOG_FILE = j_object["ResultsLogFile"]
    # MAX_GAME_TIME = j_object["MaxGameTime"]
    # REALTIME_MODE = j_object["RealTimeMode"]
    # BOTS_DIRECTORY = j_object["BaseBotDirectory"]

with open("config.py", "w+") as f:
    f.write("RUN_LOCAL = True\nTEST = True\n")

utl = Utl(config)

games = {
    '"loser_bot"vs"loser_bot" AutomatonLE.SC2Map': "Tie",
    '"basic_bot"vs"crash" AutomatonLE.SC2Map': "Player2Crash",
    '"basic_bot"vs"connect_timeout" AutomatonLE.SC2Map': "InitializationError",
    '"basic_bot"vs"crash_on_first_frame" AutomatonLE.SC2Map': "Player2Crash",
    '"basic_bot"vs"hang" AutomatonLE.SC2Map': "Player2Crash",
    '"basic_bot"vs"too_slow_bot" AutomatonLE.SC2Map': "Player2TimeOut",
    '"basic_bot"vs"instant_crash" AutomatonLE.SC2Map': "InitializationError",
    '"timeout_bot"vs"timeout_bot" AutomatonLE.SC2Map': "Tie",
    '"crash"vs"basic_bot" AutomatonLE.SC2Map': "Player1Crash",
    '"connect_timeout"vs"basic_bot" AutomatonLE.SC2Map': "Player1Crash",
    '"crash_on_first_frame"vs"basic_bot" AutomatonLE.SC2Map': "Player1Crash",
    '"hang"vs"basic_bot" AutomatonLE.SC2Map': "Player1Crash",
    '"instant_crash"vs"basic_bot" AutomatonLE.SC2Map': "Player1Crash",
    '"loser_bot"vs"basic_bot" AutomatonLE.SC2Map': "Player2Win",
    '"too_slow_bot"vs"basic_bot" AutomatonLE.SC2Map': "Player1TimeOut",
    '"basic_bot"vs"loser_bot" AutomatonLE.SC2Map': "Player1Win",
}

for key, value in games.items():

    with open("matchupList", "w+") as f:
        f.write(key)
    if key == '"loser_bot"vs"loser_bot" AutomatonLE.SC2Map':
        with open("config.py", "w+") as f:
            f.write("RUN_LOCAL = True\nTEST = True\nMAX_GAME_TIME=1000")
    else:
        with open("config.py", "w+") as f:
            f.write("RUN_LOCAL = True\nTEST = True\n")
    r = subprocess.Popen(
        [PYTHON, "aiarena-client.py"], cwd=config.WORKING_DIRECTORY, shell=True
    )
    status_code = r.wait()

    try:
        with open(RESULTS_LOG_FILE, "r") as f:
            result = json.load(f)
        test_result = f"Result ({str(result['Results'][0]['Result'])}) matches expected result ({value}):" + \
                      str(result["Results"][0]["Result"] == value)
        utl.printout(test_result)
        with open('test_results.txt', 'a+') as f:
            f.write(str(key) + '\t' + str(test_result) + '\n')
    except FileNotFoundError:
        utl.printout("Test failed: Results file not found")
    except KeyError:
        utl.printout("Test failed: Result not found in file")
