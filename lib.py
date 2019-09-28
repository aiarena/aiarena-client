import asyncio
import enum
import logging
import os
import platform
import re
from pathlib import Path
import sys
from s2clientprotocol import sc2api_pb2 as sc_pb

logger = logging.getLogger(__name__)


class Timer:
    def __init__(self, timeout, callback, args):
        self._timeout = timeout
        self._callback = callback
        self._task = asyncio.ensure_future(self._job())
        self._args = args

    async def _job(self):
        await asyncio.sleep(self._timeout)
        await self._callback(self._args)

    def cancel(self):
        self._task.cancel()


class Protocol:
    def __init__(self, ws):
        """
        :param ws:
        """
        assert ws
        self._ws = ws
        self._status = None

    async def __request(self, request):
        logger.debug(f"Sending request: {request !r}")
        try:
            await self._ws.send_bytes(request.SerializeToString())
        except TypeError:
            logger.exception("Cannot send: Connection already closed.")
            raise ConnectionAlreadyClosed("Connection already closed.")
        logger.debug(f"Request sent")

        response = sc_pb.Response()
        try:
            response_bytes = await self._ws.receive_bytes()
        except TypeError:
            # logger.exception("Cannot receive: Connection already closed.")
            # raise ConnectionAlreadyClosed("Connection already closed.")
            logger.info("Cannot receive: Connection already closed.")
            sys.exit(2)
        except asyncio.CancelledError:
            # If request is sent, the response must be received before reraising cancel
            try:
                await self._ws.receive_bytes()
            except asyncio.CancelledError:
                logger.critical("Requests must not be cancelled multiple times")
                sys.exit(2)
            raise

        response.ParseFromString(response_bytes)
        logger.debug(f"Response received")
        return response

    async def _execute(self, **kwargs):
        assert len(kwargs) == 1, "Only one request allowed"

        request = sc_pb.Request(**kwargs)

        response = await self.__request(request)

        new_status = Status(response.status)
        if new_status != self._status:
            logger.info(f"Client status changed to {new_status} (was {self._status})")
        self._status = new_status

        if response.error:
            logger.debug(f"Response contained an error: {response.error}")
            raise ProtocolError(f"{response.error}")

        return response

    async def ping(self):
        result = await self._execute(ping=sc_pb.RequestPing())
        return result

    async def quit(self):
        try:
            await self._execute(quit=sc_pb.RequestQuit())
        except ConnectionAlreadyClosed:
            pass


class AbstractPlayer:
    def __init__(
        self,
        p_type,
        race=None,
        name=None,
        difficulty=None,
        ai_build=None,
        fullscreen=False,
    ):
        assert isinstance(p_type, PlayerType), f"p_type is of type {type(p_type)}"
        assert name is None or isinstance(name, str), f"name is of type {type(name)}"

        self.name = name
        self.type = p_type
        self.fullscreen = fullscreen
        if race is not None:
            self.race = race

        assert difficulty is None
        assert ai_build is None


class Bot(AbstractPlayer):
    def __init__(self, race, ai, name=None, fullscreen=False):
        """
        AI can be None if this player object is just used to inform the
        server about player types.
        """
        super().__init__(PlayerType.Participant, race, name=name, fullscreen=fullscreen)
        self.ai = ai

    def __str__(self):
        if self.name is not None:
            return f"Bot(Unknown, {self.ai}, name={self.name !r})"
        else:
            return f"Bot(Unknown, {self.ai})"


class ProtocolError(Exception):
    @property
    def is_game_over_error(self) -> bool:
        return self.args[0] in [
            "['Game has already ended']",
            "['Not supported if game has already ended']",
        ]


class ConnectionAlreadyClosed(ProtocolError):
    pass


class Controller(Protocol):
    def __init__(self, ws, process):
        super().__init__(ws)
        self.__process = process

    @property
    def running(self):
        return self.__process._process is not None

    async def create_game(self, game_map, players, realtime, random_seed=None):
        assert isinstance(realtime, bool)
        req = sc_pb.RequestCreateGame(
            local_map=sc_pb.LocalMap(map_path=str(game_map.relative_path)),
            realtime=realtime,
        )
        if random_seed is not None:
            req.random_seed = random_seed

        for player in players:
            p = req.player_setup.add()
            p.type = player.type.value
            p.player_name = player.name

        logger.debug("Creating new game")
        logger.debug(f"Map:     {game_map.name}")
        logger.debug(f"Players: {', '.join(str(p) for p in players)}")
        result = await self._execute(create_game=req)

        return result


BASEDIR = {
    "Windows": "C:/Program Files (x86)/StarCraft II",
    "Darwin": "/Applications/StarCraft II",
    "Linux": "~/StarCraftII",
    "WineLinux": "~/.wine/drive_c/Program Files (x86)/StarCraft II",
}

USERPATH = {
    "Windows": "\\Documents\\StarCraft II\\ExecuteInfo.txt",
    "Darwin": "/Library/Application Support/Blizzard/StarCraft II/ExecuteInfo.txt",
    "Linux": None,
    "WineLinux": None,
}

BINPATH = {
    "Windows": "SC2_x64.exe",
    "Darwin": "SC2.app/Contents/MacOS/SC2",
    "Linux": "SC2_x64",
    "WineLinux": "SC2_x64.exe",
}

CWD = {"Windows": "Support64", "Darwin": None, "Linux": None, "WineLinux": "Support64"}

PF = os.environ.get("SC2PF", platform.system())


def get_env():
    # TODO: Linux env conf from: https://github.com/deepmind/pysc2/blob/master/pysc2/run_configs/platforms.py
    return None


def latest_executeble(versions_dir):
    latest = max((int(p.name[4:]), p) for p in versions_dir.iterdir() if p.is_dir() and p.name.startswith("Base"))
    version, path = latest
    if version < 55958:
        logger.critical(f"Your SC2 binary is too old. Upgrade to 3.16.1 or newer.")
        exit(1)
    return path / BINPATH[PF]


class _MetaPaths(type):
    """"Lazily loads paths to allow importing the library even if SC2 isn't installed."""

    def __setup(self):
        if PF not in BASEDIR:
            logger.critical(f"Unsupported platform '{PF}'")
            exit(1)

        try:
            base = os.environ.get("SC2PATH")
            if base is None and USERPATH[PF] is not None:
                einfo = str(Path.home().expanduser()) + USERPATH[PF]
                if os.path.isfile(einfo):
                    with open(einfo) as f:
                        content = f.read()
                    if content:
                        base = re.search(r" = (.*)Versions", content).group(1)
                        if not os.path.exists(base):
                            base = None
            if base is None:
                base = BASEDIR[PF]
            self.BASE = Path(base).expanduser()
            self.EXECUTABLE = latest_executeble(self.BASE / "Versions")
            self.CWD = self.BASE / CWD[PF] if CWD[PF] else None

            self.REPLAYS = self.BASE / "Replays"

            if (self.BASE / "maps").exists():
                self.MAPS = self.BASE / "maps"
            else:
                self.MAPS = self.BASE / "Maps"
        except FileNotFoundError as e:
            logger.critical(f"SC2 installation not found: File '{e.filename}' does not exist.")
            exit(1)

    def __getattr__(self, attr):
        self.__setup()
        return getattr(self, attr)


class Paths(metaclass=_MetaPaths):
    """Paths for SC2 folders, lazily loaded using the above metaclass."""


PlayerType = enum.Enum("PlayerType", sc_pb.PlayerType.items())
Status = enum.Enum("Status", sc_pb.Status.items())
Result = enum.Enum("Result", sc_pb.Result.items())
ChatChannel = enum.Enum("ChatChannel", sc_pb.ActionChat.Channel.items())
