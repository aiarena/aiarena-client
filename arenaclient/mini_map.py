import traceback
import numpy as np
import cv2
from arenaclient.sc2 import game_state, game_info, cache, game_data, unit


class Minimap:
    def __init__(
            self,
            map_scale=1,
            player_name=None
    ):
        self.map_scale = map_scale
        self._game_info = None
        self._state = None
        self._game_data = None
        self.player_name = player_name

        self.colors = {
            "ally_units": (0, 255, 0),
            "enemy_units": (0, 0, 255),
            "psi": (240, 240, 140),
            "creep": (73, 33, 63),
            "geysers": (60, 160, 100),
            "minerals": (220, 180, 140),
            "destructables": (80, 100, 120),
            "vision_blockers": (0, 0, 0),
            "ramp": (110, 100, 100),
            "upperramp": (120, 110, 110),
            "lowerramp": (100, 90, 90),
            "xelnaga": (170, 200, 100),
        }

    def draw_map(self):
        try:

            map_data = np.copy(self.heightmap)
            self.add_minerals(map_data)
            self.add_geysers(map_data)
            self.add_allies(map_data)
            self.add_enemies(map_data)
            
            flipped = cv2.flip(map_data, 0)
            font = cv2.FONT_HERSHEY_SIMPLEX
            org = (50, 50)
            # font_scale
            font_scale = 1
            # Blue color in BGR
            color = (50, 194, 134)
            # Line thickness of 2 px
            thickness = 1
            
            flipped = cv2.resize(flipped, (500, 500), cv2.INTER_NEAREST)
            cv2.putText(flipped, self.player_name, org, font, font_scale, color, thickness, cv2.LINE_AA)
            return flipped

        except Exception:
            print(traceback.format_exc())

    @cache.property_cache_forever
    def empty_map(self):
        map_scale = self.map_scale
        map_data = np.zeros(
            (
                self._game_info.map_size[1] * map_scale,
                self._game_info.map_size[0] * map_scale,
                3,
            ),
            np.uint8,
        )
        return map_data

    @cache.property_cache_forever
    def heightmap(self):
        # gets the min and max heigh of the map for a better contrast
        h_min = np.amin(self._game_info.terrain_height.data_numpy)
        h_max = np.amax(self._game_info.terrain_height.data_numpy)
        multiplier = 160 / (h_max - h_min)

        map_data = self.empty_map

        for (y, x), h in np.ndenumerate(self._game_info.terrain_height.data_numpy):
            color = (h - h_min) * multiplier
            cv2.rectangle(
                map_data,
                (int(x * self.map_scale), int(y * self.map_scale)),
                (
                    int(x * self.map_scale + self.map_scale),
                    int(y * self.map_scale + self.map_scale),
                ),
                (color * 18 / 20, color * 19 / 20, color),
                int(-1),
            )
        return map_data
    
    def get_score(self):
        score_image = np.ones((500, 500, 3))
        i = 0
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_size = 1
        font_thickness = 1
        color = (50, 194, 134)
        wrapped_text = [
            'Score: ' + str(self._state.score.score),
            'Time: ' + f"{int((self._state.game_loop/22.4) // 60):02}:{int((self._state.game_loop/22.4) % 60):02}",
            'Minerals: ' + str(self._state.common.minerals),
            'Vespene: ' + str(self._state.common.vespene),
            'Units Value: ' + str(self._state.score.total_value_units)
            ]
        for line in wrapped_text:
            line = str(line)
            textsize = cv2.getTextSize(line, font, font_size, font_thickness)[0]

            gap = textsize[1] + 10

            y = int((score_image.shape[0] + textsize[1]) / 2) + i * gap
            x = int((score_image.shape[1] - textsize[0]) / 2)

            cv2.putText(score_image, line, (x, y), font,
                        font_size, 
                        color, 
                        font_thickness, 
                        lineType=cv2.LINE_AA)
            i += 1
        return score_image
    
    def add_minerals(self, map_data):
        for mineral in self._state.mineral_field:
            mine_pos = mineral.position
            cv2.rectangle(
                map_data,
                (
                    int((mine_pos[0] - 0.75) * self.map_scale),
                    int((mine_pos[1] - 0.25) * self.map_scale),
                ),
                (
                    int((mine_pos[0] + 0.75) * self.map_scale),
                    int((mine_pos[1] + 0.25) * self.map_scale),
                ),
                self.colors["minerals"],
                -1,
            )

    def add_geysers(self, map_data):
        for g in self._state.vespene_geyser:
            g_pos = g.position
            cv2.rectangle(
                map_data,
                (
                    int((g_pos[0] - g.radius) * self.map_scale),
                    int((g_pos[1] - g.radius) * self.map_scale),
                ),
                (
                    int((g_pos[0] + g.radius) * self.map_scale),
                    int((g_pos[1] + g.radius) * self.map_scale),
                ),
                self.colors["geysers"],
                -1,
            )

    def add_allies(self, map_data):
        for ally in self._state.own_units:
            if ally.is_structure:
                cv2.rectangle(
                    map_data,
                    (
                        int((ally.position[0] - ally.radius) * self.map_scale),
                        int((ally.position[1] - ally.radius) * self.map_scale),
                    ),
                    (
                        int((ally.position[0] + ally.radius) * self.map_scale),
                        int((ally.position[1] + ally.radius) * self.map_scale),
                    ),
                    self.colors["ally_units"],
                    -1,
                )
            else:
                cv2.circle(
                    map_data,
                    (
                        int(ally.position[0] * self.map_scale),
                        int(ally.position[1] * self.map_scale),
                    ),
                    int(ally.radius * self.map_scale),
                    self.colors["ally_units"],
                    -1,
                )

    def add_enemies(self, map_data):
        for enemy in self._state.enemy_units:
            if enemy.is_structure:
                cv2.rectangle(
                    map_data,
                    (
                        int((enemy.position[0] - enemy.radius) * self.map_scale),
                        int((enemy.position[1] - enemy.radius) * self.map_scale),
                    ),
                    (
                        int((enemy.position[0] + enemy.radius) * self.map_scale),
                        int((enemy.position[1] + enemy.radius) * self.map_scale),
                    ),
                    self.colors["enemy_units"],
                    -1,
                )
            else:
                cv2.circle(
                    map_data,
                    (
                        int(enemy.position[0] * self.map_scale),
                        int(enemy.position[1] * self.map_scale),
                    ),
                    int(enemy.radius * self.map_scale),
                    (0, 0, 255),
                    -1,
                )

    def load_game_info(self, data):
        self._game_info = game_info.GameInfo(data.game_info)

    def load_state(self, data):
        self._state = game_state.GameState(data.observation)

    def load_game_data(self, data):
        self._game_data = game_data.GameData(data.data)
        unit.UnitGameData._game_data = self._game_data
