import numpy as np

class PixelMap:
    def __init__(self, proto):
        self._proto = proto
        buffer_data = np.frombuffer(self._proto.data, dtype=np.uint8)
        self.data_numpy = buffer_data.reshape(self._proto.size.y, self._proto.size.x)