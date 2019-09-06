from sc2.data import PlayerType
import logging
from s2clientprotocol import sc2api_pb2 as sc_pb
import asyncio
from sc2.protocol import Protocol
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


class AbstractPlayer:
    def __init__(self, p_type, race=None, name=None, difficulty=None, ai_build=None, fullscreen=False):
        assert isinstance(
            p_type, PlayerType), f"p_type is of type {type(p_type)}"
        assert name is None or isinstance(
            name, str), f"name is of type {type(name)}"

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
        return self.args[0] in ["['Game has already ended']", "['Not supported if game has already ended']"]


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
        req = sc_pb.RequestCreateGame(local_map=sc_pb.LocalMap(
            map_path=str(game_map.relative_path)), realtime=realtime)
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
