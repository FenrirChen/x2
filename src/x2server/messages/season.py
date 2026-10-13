"""Season messages whose field tags were checked against native 2.4 Serialize."""
import json
from importlib.resources import files
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema

WIRE = json.loads(files('x2server').joinpath('data/season_wire.json').read_text('utf8'))
PRIMITIVES = {'int': K.INT32, 'long': K.INT64, 'bool': K.BOOL, 'string': K.STRING}
SEASON_SCHEMAS = {name: ProtoSchema(name, tuple(F(f['number'], f['name'],
    PRIMITIVES.get(f['type'], K.MESSAGE if f['type'] in WIRE['schemas'] else K.ENUM),
    repeated=f['repeated']) for f in definition['fields'])) for name, definition in WIRE['schemas'].items()}
SEASON_IDS = tuple((name[4:], mid, WIRE['ids']['L2C_' + name[4:]])
    for name, mid in WIRE['ids'].items() if name.startswith('C2L_'))
SEASON_PUSH_IDS = tuple((name, mid) for name, mid in WIRE['ids'].items()
    if name.startswith('L2C_') and 'C2L_' + name[4:] not in WIRE['ids'])


def encode(name, values):
    """Supply non-null nested containers required by SilentOrbit consumers."""
    result = dict(values)
    for field in WIRE['schemas'][name]['fields']:
        key, kind = field['name'], field['type']
        nested = kind in SEASON_SCHEMAS
        if field['repeated']:
            entries = result.get(key) or ([{}] if nested else [0])
            result[key] = [encode(kind, entry) if isinstance(entry, dict) else entry for entry in entries] if nested else entries
        elif nested:
            entry = result.get(key, {})
            result[key] = encode(kind, entry) if isinstance(entry, dict) else entry
    return SEASON_SCHEMAS[name].encode(result)
