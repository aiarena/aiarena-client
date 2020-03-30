from .cache import property_immutable_cache
from .position import Point2
from .data import Attribute


class UnitGameData:
    """ Populated by sc2/main.py on game launch.
    Used in PassengerUnit, Unit, Units and UnitOrder. """

    # TODO: When doing bot vs bot, the same _game_data is currently accessed if the laddermanager
    # is not being used and the bots access the same sc2 library
    # Could use inspect for that: Loop over i for "calframe[i].frame.f_locals["self"]"
    # until an instance of BotAi is found
    _game_data = None
    _bot_object = None


class Unit:
    def __init__(self, proto_data):
        self._proto = proto_data
        self.cache = {}

    @property
    def is_structure(self) -> bool:
        """ Checks if the unit is a structure. """
        return Attribute.Structure.value in self._type_data.attributes

    @property_immutable_cache
    def position(self) -> Point2:
        """ Returns the 2d position of the unit. """
        return Point2.from_proto(self._proto.pos)
    
    @property_immutable_cache
    def radius(self):
        """ Half of unit size. See https://liquipedia.net/starcraft2/Unit_Statistics_(Legacy_of_the_Void) """
        return self._proto.radius
    
    @property_immutable_cache
    def _type_data(self):
        """ Provides the unit type data. """
        return UnitGameData._game_data.units[self._proto.unit_type]
