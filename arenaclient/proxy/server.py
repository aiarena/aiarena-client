import argparse
import asyncio
import logging
import os
import signal
import threading
import traceback
import weakref

import aiohttp_jinja2
import jinja2
import psutil
from aiohttp import web, MultipartWriter

from arenaclient.proxy import frontend

try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ModuleNotFoundError:
    print("Uvloop not found, using default asyncio")
    pass

from arenaclient.proxy.lib import Timer
from arenaclient.proxy.port_config import Portconfig
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
        self.port_config: Portconfig = None
        self.supervisor: Supervisor = None
        self.t1: Timer = None
        self.t2: Timer = None

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

    async def stream_handler(self, request):
        import numpy as np
        import cv2
        boundary = "boundarydonotcross"
        resp = web.StreamResponse(status=200, reason='OK', headers={
            'Content-Type': 'multipart/x-mixed-replace; '
                            'boundary=--%s' % boundary,
        })
        await resp.prepare(request)
        
        while True:
            await asyncio.sleep(0.1)
            if self.supervisor and self.supervisor.images is not None:
                output_frame = await self.supervisor.build_montage()
                
                # await ws.send_bytes(self.supervisor.image)
            else:
                await asyncio.sleep(1)
                output_frame = np.ones((500, 500, 3), dtype=np.uint8)

            if output_frame is None:
                output_frame = np.ones((500, 500, 3), dtype=np.uint8)

            # encode the frame in JPEG format
            (flag, encodedImage) = cv2.imencode(".jpg", output_frame)
            with MultipartWriter('image/jpeg', boundary=boundary) as mpwriter:
                data = encodedImage.tostring()
                mpwriter.append(data, {
                    'Content-Type': 'image/jpeg'
                })
                # asyncio.create_task( mpwriter.write(response, close_boundary=False))
                await mpwriter.write(resp, close_boundary=False)
                
        # while True:
        #     if self.supervisor and self.supervisor.image:
        #         output_frame = self.supervisor.image
                
        #         # await ws.send_bytes(self.supervisor.image)
        #     else:
        #         output_frame = np.ones((500,500,3),dtype=np.uint8).tobytes()
        #         # await ws.send_bytes(np.ones((500,500,3),dtype=np.uint8).tobytes())
        #         # asyncio.sleep(10)
        #         # continue
        #     await resp.drain()
        #     # await ws.write(b'')

        return resp


    async def websocket_handler(self, request):
        """
        Creates supervisor and proxy objects for all connections.

        :param request:
        :return:
        """
        if bool(request.headers.get("Supervisor", False)):  # Checks if a supervisor has requested to connect
            logger.debug("Using supervisor")
            self.supervisor = Supervisor()

            self.t1 = Timer(40, self.bots_connected, args=[request, 1])  # Calls bots_connected after 40 seconds.
            await self.supervisor.websocket_handler(request)  # Sends request to the supervisor.

        elif self.supervisor is not None:
            logger.debug("Connecting bot with supervisor")
            if not self.port_config:
                # Needs to figure out the ports for both bots at the same time
                self.port_config = Portconfig()
            if len(request.app["websockets"]) == 1:  # Only supervisor is connected

                logger.debug("First bot connecting")
                await self.supervisor.send_message({"Bot": "Connected"})

                self.t2 = Timer(40, self.bots_connected, args=[request, 2])  # Calls bots_connected after 40 seconds.

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
                    max_frame_time=self.supervisor.max_frame_time,
                    real_time=self.supervisor.real_time,
                    visualize=self.supervisor.visualize,
                    visualize_port=5556

                )
                await proxy1.websocket_handler(request, self.port_config)

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
                    max_frame_time=self.supervisor.max_frame_time,
                    real_time=self.supervisor.real_time,
                    visualize=self.supervisor.visualize,
                    visualize_port=5557
                )
                await proxy2.websocket_handler(request, self.port_config)

        else:  # TODO: Implement this for devs running without a supervisor
            raise NotImplementedError
            logger.debug("Connecting bot without supervisor")
            if not self.port_config:
                # Needs to figure out the ports for both bots at the same time
                self.port_config = Portconfig()
            self.connected_clients += 1
            if self.connected_clients == 1:
                proxy1 = Proxy(game_created=False)
                await proxy1.websocket_handler(request, self.port_config)
            else:
                proxy2 = Proxy(game_created=True)
                await proxy2.websocket_handler(request, self.port_config)
        if self.t1:
            self.t1.cancel()

        if self.t2:
            self.t2.cancel()

        self.__init__()
        return web.Response(text="OK")


def on_start():
    try:

        for process in psutil.process_iter():
            for conns in process.connections(kind="inet"):
                if conns.laddr.port == PORT:
                    try:
                        process.send_signal(signal.SIGTERM)
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        pass
            if process.name() == "SC2_x64.exe":
                try:
                    process.send_signal(signal.SIGTERM)
                except psutil.AccessDenied:
                    pass
    except:
        print(traceback.format_exc())
        pass


def run_server():
    """
    Starts the proxy application on HOST and PORT, which defaults to '127.0.0.1' and 8765.

    HOST and PORT can be set using environment variables of the same name.

    :return:
    """
    parser = argparse.ArgumentParser()

    # TODO: Change default to false
    parser.add_argument("-f", "--frontend", type=bool, nargs="?", help="Start server with frontend", default=True)
    args, unknown = parser.parse_known_args()

    try:
        loop = asyncio.get_event_loop()
    except:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    app = web.Application()
    app.shutdown()
    app.router.add_static('/static', 'static')
    app._loop = loop
    # app._client_max_size = 3
    app["websockets"] = weakref.WeakSet()
    connection = ConnectionHandler()
    app.router.add_route("GET", "/sc2api", connection.websocket_handler)
    if args.frontend:
        print('launching with frontend')
        t = threading.Thread(target=frontend.detect_motion)
        t.daemon = True
        t.start()
        aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader('templates'))
        app['static_root_url'] = '/static'
        routes = [
            web.get("/", frontend.index, name='index'),
            web.get("/video_feed", connection.stream_handler, name='video_feed'),
            web.get("/settings", frontend.settings, name='settings'),
            web.get("/watch", frontend.watch, name='watch'),
            web.post("/clear_results", frontend.clear_results, name='clear_results'),
            web.post("/handle_data", frontend.handle_data, name='handle_data'),
            web.get("/get_settings", frontend.get_settings, name='get_settings'),
            web.get("/get_results", frontend.get_results, name='get_results'),
            web.post("/run_games", frontend.run_games, name='run_games'),
            web.get("/get_bots", frontend.get_bots, name='get_bots'),
            web.get("/get_arena_bots", frontend.get_arena_bots, name='get_arena_bots'),
            web.get("/get_maps", frontend.get_maps, name='get_maps')
        ]
        app.router.add_routes(routes)
        # app.router.add_route("GET","/", frontend.hello, name='hello')
    on_start()
    try:
        web.run_app(app, host=HOST, port=PORT)  # HOST and PORT can be set using environment variables
    except KeyboardInterrupt:
        app.shutdown()


if __name__ == "__main__":
    run_server()



