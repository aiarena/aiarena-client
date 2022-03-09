
import multiprocessing
import os
import sys

import arenaclient.__main__

if __name__ == "__main__":  # execute only if run as a script
    sys.path.append(os.path.dirname(sys.executable))  # so we can import a local config file
    multiprocessing.freeze_support()
    arenaclient.__main__.main()


# build commands:
# pyinstaller --onefile --add-data "sc2;sc2/" --name basic_bot run.py
# pyinstaller --onefile --add-data "sc2;sc2/" --name loser_bot run.py
# pyinstaller --onefile --add-data "./arenaclient/configs/config.py;./" .\main.py