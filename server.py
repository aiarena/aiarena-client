import logging
import os
import weakref

import aiohttp
from aiohttp import web
from portconfig import Portconfig

from lib import Timer
from proxy import Proxy
from supervisor import Supervisor

HOST = os.getenv("HOST", "127.0.0.1")
PORT = int(os.getenv("PORT", 8765))
logger = logging.getLogger(__name__)
logger.setLevel(10)



class ConnectionHandler:
    def __init__(self):
        self.connected_clients = 0
        self.portconfig = None
        self.supervisor = None
        self.result = []

    async def bots_connected(self, args):
        request = args[0]
        expected = args[1]
        if not len(request.app["websockets"]) > expected:
            logger.debug("Bots did not connect in time")
            await self.supervisor.send_message(
                dict({"Bot": "Bot did not connect in time"})
            )
            # await self.supervisor.close()

    async def websocket_handler(self, request):
        if bool(request.headers.get("Supervisor", False)):
            logger.debug("Using supervisor")
            self.supervisor = Supervisor()

            Timer(40, self.bots_connected, args=[request, 1])

            await self.supervisor.websocket_handler(request)

        elif self.supervisor is not None:
            logger.debug("Connecting bot with supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            if len(request.app["websockets"]) == 1:
                # game_created =False forces first player to create game when both players are connected.
                logger.debug("First bot connecting")
                await self.supervisor.send_message({"Bot": "Connected"})

                Timer(40, self.bots_connected, args=[request, 2])

                proxy1 = Proxy(
                    game_created=False,
                    player_name=self.supervisor.player1,
                    opponent_name=self.supervisor.player2,
                    max_game_time=self.supervisor.max_game_time,
                    map_name=self.supervisor.map,
                    replay_name=self.supervisor.replay_name,
                    disable_debug=bool(self.supervisor.disable_debug),
                    supervisor=self.supervisor,
                    strikes=self.supervisor.strikes,
                    max_frame_time=self.supervisor.max_frame_time
                )
                await proxy1.websocket_handler(request, self.portconfig)

            elif len(request.app["websockets"]) == 2:
                logger.debug("Second bot connecting")
                await self.supervisor.send_message({"Bot": "Connected"})
                proxy2 = Proxy(
                    game_created=True,
                    player_name=self.supervisor.player2,
                    opponent_name=self.supervisor.player1,
                    max_game_time=self.supervisor.max_game_time,
                    map_name=self.supervisor.map,
                    replay_name=self.supervisor.replay_name,
                    disable_debug=bool(self.supervisor.disable_debug),
                    supervisor=self.supervisor,
                    strikes=self.supervisor.strikes,
                    max_frame_time=self.supervisor.max_frame_time
                )
                await proxy2.websocket_handler(request, self.portconfig)

        else:  # TODO: Implement this for devs running without a supervisor
            logger.debug("Connecting bot without supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            self.connected_clients += 1
            if self.connected_clients == 1:
                # game_created =False forces first player to create game when both players are connected.
                proxy1 = Proxy(game_created=False)
                await proxy1.websocket_handler(request, self.portconfig)
            else:  # This breaks when there are more than 2 connections. TODO: fix
                proxy2 = Proxy(game_created=True)
                await proxy2.websocket_handler(request, self.portconfig)

        return web.Response(text="OK")


def main():
    app = web.Application()
    app["websockets"] = weakref.WeakSet()
    connection = ConnectionHandler()
    app.router.add_route("GET", "/sc2api", connection.websocket_handler)
    # aiohttp_debugtoolbar.setup(app)
    web.run_app(app, host=HOST, port=PORT)



if __name__ == "__main__":
    main()
