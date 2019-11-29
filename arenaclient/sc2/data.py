import enum
from s2clientprotocol import data_pb2 as data_pb

Attribute = enum.Enum("Attribute", data_pb.Attribute.items())
