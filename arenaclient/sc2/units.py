from .unit import Unit


class Units(list):
    """A collection of Unit objects. Makes it easy to select units by selectors."""
    @classmethod
    def from_proto(cls, units, game_data=None):
        return cls((Unit(u) for u in units))

    def __init__(self, units, game_data=None):
        super().__init__(units)
