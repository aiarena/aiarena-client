from arenaclient.proxy.server import run_server
from multiprocessing import Process
from time import sleep
from cefpython3 import cefpython_py37 as cef
import sys


if __name__ == "__main__":
    proc = Process(target=run_server, args=(True,))
    proc.daemon = True
    proc.start()
    sleep(2)
    sys.excepthook = cef.ExceptHook  # To shutdown all CEF processes on error
    cef.Initialize()
    cef.CreateBrowserSync(url="http://127.0.0.1:8765",
                          window_title="Match Runner", settings={'web_security_disabled': True,
                                                                 'background_color': 16000000})
    cef.MessageLoop()
    # cef.
    cef.Shutdown()
