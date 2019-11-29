from .pixel_map import PixelMap
from .position import Rect, Size


class GameInfo:
    def __init__(self, proto):
        self._proto = proto
        self.map_size: Size = Size.from_proto(self._proto.start_raw.map_size)
        self.terrain_height: PixelMap = PixelMap(self._proto.start_raw.terrain_height)
        self.playable_area = Rect.from_proto(self._proto.start_raw.playable_area)
        # self.map_center = self.playable_area.center
