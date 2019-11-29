class GameData:
    def __init__(self, data):
        self.units = {u.unit_id: UnitTypeData(self, u) for u in data.units if u.available}


class UnitTypeData:
    def __init__(self, game_data, proto):
        self._game_data = game_data
        self._proto = proto

    @property
    def attributes(self):
        return self._proto.attributes
