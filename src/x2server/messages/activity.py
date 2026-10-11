"""Activity protocols verified against the native 2.4 serializers."""
import json
from importlib.resources import files
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema
from .lobby import LOBBY_IDS

_data = json.loads(files('x2server').joinpath('data/activity_wire.json').read_text(encoding='utf-8'))
_primitive = {'int': K.INT32, 'long': K.INT64, 'bool': K.BOOL, 'string': K.STRING}
ACTIVITY_SCHEMAS = {
    name: ProtoSchema(name, tuple(F(field['number'], field['name'],
        _primitive.get(field['type'], K.MESSAGE if field['type'] in _data['schemas'] else K.ENUM),
        repeated=field['repeated']) for field in definition['fields']))
    for name, definition in _data['schemas'].items()
}
ACTIVITY_MESSAGE_IDS = _data['ids']
_existing = {name for name, _, _ in LOBBY_IDS}
ACTIVITY_IDS = tuple((name[4:], mid, ACTIVITY_MESSAGE_IDS['L2C_' + name[4:]])
    for name, mid in ACTIVITY_MESSAGE_IDS.items()
    if name.startswith('C2L_') and name[4:] not in _existing)
ACTIVITY_PUSH_IDS = tuple((name, mid) for name, mid in ACTIVITY_MESSAGE_IDS.items()
    if name.startswith('L2C_') and 'C2L_' + name[4:] not in ACTIVITY_MESSAGE_IDS)


def encode(name, values):
    return ACTIVITY_SCHEMAS[name].encode(values)
