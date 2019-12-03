from .constants import geyser_ids, mineral_ids
from .score import ScoreDetails
from .unit import Unit
from .units import Units


class Common:
    ATTRIBUTES = [
        "player_id",
        "minerals", "vespene",
        "food_cap", "food_used",
        "food_army", "food_workers",
        "idle_worker_count", "army_count",
        "warp_gate_count", "larva_count"
    ]

    def __init__(self, proto):
        self._proto = proto

    def __getattr__(self, attr):
        assert attr in self.ATTRIBUTES, f"'{attr}' is not a valid attribute"
        return int(getattr(self._proto, attr))


class GameState:
    def __init__(self, response_observation):
        self.observation = response_observation.observation
        self.common: Common = Common(self.observation.player_common)
        self.game_loop: int = self.observation.game_loop  # 22.4 per second on faster game speed
        self.score: ScoreDetails = ScoreDetails(self.observation.score)
        self.own_units: Units = Units([])
        self.enemy_units: Units = Units([])
        self.mineral_field: Units = Units([])
        self.vespene_geyser: Units = Units([])
        self.resources: Units = Units([])
        self.destructables: Units = Units([])
        self.watchtowers: Units = Units([])
        self.units: Units = Units([])
        
    async def _init(self):
        for unit in self.observation.raw_data.units:
            if unit.is_blip:
                continue
            else:
                unit_obj = Unit(unit)
                self.units.append(unit_obj)
                alliance = unit.alliance
                if alliance == 3:
                    unit_type = unit.unit_type
                    if unit_type == 149:
                        self.watchtowers.append(unit_obj)
                    elif unit_type in mineral_ids:
                        self.mineral_field.append(unit_obj)
                        self.resources.append(unit_obj)
                    elif unit_type in geyser_ids:
                        self.vespene_geyser.append(unit_obj)
                        self.resources.append(unit_obj)
                    else:
                        self.destructables.append(unit_obj)
                elif alliance == 1:
                    self.own_units.append(unit_obj)
                elif alliance == 4:
                    self.enemy_units.append(unit_obj)
