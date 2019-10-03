import logging
import os
import weakref


from aiohttp import web
from arenaclient.proxy.portconfig import Portconfig

from arenaclient.lib import Timer
from arenaclient.proxy.proxy import Proxy
from arenaclient.proxy.supervisor import Supervisor

HOST = os.getenv("HOST", "127.0.0.1")  # Environment variables for ease of access.
PORT = int(os.getenv("PORT", 8765))
logger = logging.getLogger(__name__)
logger.setLevel(10)


class ConnectionHandler:
    """
    Handles all connections and creates the relevant objects.
    """
    def __init__(self):
        self.connected_clients: int = 0
        self.portconfig = None
        self.supervisor = None

    async def bots_connected(self, args):
        """
        Called by Timer() after a specified amount of time. Checks if the connected clients is equal to the expected
        number of connected clients, and sends an error message to the supervisor client if it isn't.

        :param args:
        :return:
        """
        request = args[0]
        expected = args[1]
        if not len(request.app["websockets"]) > expected:
            logger.debug("Bots did not connect in time")
            await self.supervisor.send_message(
                dict({"Bot": "Bot did not connect in time"})
            )

    async def websocket_handler(self, request):
        """
        Creates supervisor and proxy objects for all connections.

        :param request:
        :return:
        """
        if bool(request.headers.get("Supervisor", False)):  # Checks if a supervisor has requested to connect
            logger.debug("Using supervisor")
            self.supervisor = Supervisor()

            Timer(40, self.bots_connected, args=[request, 1])  # Calls bots_connected after 40 seconds.

            await self.supervisor.websocket_handler(request)  # Sends request to the supervisor.

        elif self.supervisor is not None:
            logger.debug("Connecting bot with supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            if len(request.app["websockets"]) == 1:  # Only supervisor is connected

                logger.debug("First bot connecting")
                await self.supervisor.send_message({"Bot": "Connected"})

                Timer(40, self.bots_connected, args=[request, 2])  # Calls bots_connected after 40 seconds.

                # game_created =False forces first player to create game when both players are connected.
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

            elif len(request.app["websockets"]) == 2:  # Supervisor and bot 1 connected.
                logger.debug("Second bot connecting")
                await self.supervisor.send_message({"Bot": "Connected"})

                proxy2 = Proxy(
                    game_created=True,  # Game has already been created by Bot 1.
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
            raise NotImplementedError
            logger.debug("Connecting bot without supervisor")
            if not self.portconfig:
                # Needs to figure out the ports for both bots at the same time
                self.portconfig = Portconfig()
            self.connected_clients += 1
            if self.connected_clients == 1:
                proxy1 = Proxy(game_created=False)
                await proxy1.websocket_handler(request, self.portconfig)
            else:
                proxy2 = Proxy(game_created=True)
                await proxy2.websocket_handler(request, self.portconfig)

        return web.Response(text="OK")


def main():
    """
    Starts the proxy application on HOST and PORT, which defaults to '127.0.0.1' and 8765.

    HOST and PORT can be set using environment variables of the same name.

    :return:
    """
    app = web.Application()
    app["websockets"] = weakref.WeakSet()
    connection = ConnectionHandler()
    app.router.add_route("GET", "/sc2api", connection.websocket_handler)  # Default route bots connect to.
    web.run_app(app, host=HOST, port=PORT)  # HOST and PORT can be set using environment variables


if __name__ == "__main__":
    main()
