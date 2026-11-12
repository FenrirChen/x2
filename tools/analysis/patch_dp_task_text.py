"""Patch the client DP task text without touching task conditions.

Build-time only: rewrites the Language row used by 650810 so its wording matches
the server-side 3500 target. The replacement string has the same byte length, so
the RSA-covered prefix and the record framing stay byte-identical.
"""
import argparse, hashlib, json, sys, zipfile
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent)]
import UnityPy
from _client_table_wire import convert_data_bytes, parse_message, parse_table_container, rsa_public_unpad

RESOURCE = 'table/language'
LANG_KEY = 6508101
OLD_TEXT = b'4500'
NEW_TEXT = b'3500'


def xor_table(blob):
    out = bytearray(blob)
    index, delta = 1, 0
    while index < len(out):
        out[index] ^= (delta + index) & 255
        index <<= 1
        delta -= 1
    index, delta = len(out) - 1, 0
    while index > 0:
        out[index] ^= (delta + index) & 255
        index >>= 1
        delta -= 1
    return bytes(out)


def locate_table(archive):
    environment = UnityPy.load(archive.read('assets/bin/Data/globalgamemanagers'))
    serialized = next(iter(environment.files.values()))
    manager = next(o for o in environment.objects if o.type.name == 'ResourceManager').read_typetree()
    for resource, pointer in manager['m_Container']:
        if resource != RESOURCE:
            continue
        external = serialized.externals[pointer['m_FileID'] - 1].path
        return external, pointer['m_PathID']
    raise ValueError(f'{RESOURCE} missing from ResourceManager')


def rewritten_plain(plain):
    """Return (patched_plain, absolute_offset) for the single target row."""
    hits = []
    fields, _ = parse_message(plain, 4)
    for field in fields:
        if field.field != 2 or field.wire != 2:
            continue
        values, _ = parse_message(field.value)
        key = next(v.value for v in values if v.field == 1 and v.wire == 0)
        if key != LANG_KEY:
            continue
        text = next(v for v in values if v.field == 2 and v.wire == 2)
        assert text.value.count(OLD_TEXT) == 1, 'expected a single 4500 in the task text'
        row_start = field.end - len(field.value)
        payload_start = text.end - len(text.value)
        hits.append(row_start + payload_start + text.value.index(OLD_TEXT))
    assert len(hits) == 1, 'language key not found exactly once'
    offset = hits[0]
    return plain[:offset] + NEW_TEXT + plain[offset + len(NEW_TEXT):], offset


def patch(apk, output):
    with zipfile.ZipFile(apk) as z:
        external, path_id = locate_table(z)
        source = z.read('assets/bin/Data/' + external)
    env = UnityPy.load(source)
    text = next(o for o in env.objects if o.type.name == 'TextAsset' and o.path_id == path_id)
    tree = text.read_typetree()
    script = tree['m_Script']
    encrypted = script.encode('utf-8', 'surrogateescape') if isinstance(script, str) else script

    container = parse_table_container(encrypted)
    assert container['kind'] == 'array'
    plain = container['plain']
    repaired, offset = rewritten_plain(plain)
    assert len(repaired) == len(plain) and repaired[offset:offset + 4] == NEW_TEXT

    signed_prefix = rsa_public_unpad(encrypted[:128])
    obfuscated = xor_table(repaired)
    assert obfuscated[:len(signed_prefix)] == signed_prefix, 'RSA-covered prefix changed'
    patched = encrypted[:128] + obfuscated[len(signed_prefix):]
    assert len(patched) == len(encrypted)
    assert convert_data_bytes(patched) == repaired

    decoded = parse_table_container(patched)
    assert decoded['keys'] == container['keys'] and len(decoded['items']) == len(container['items'])
    row = next(item for key, item in zip(decoded['keys'], decoded['items']) if key == LANG_KEY)
    row_values, _ = parse_message(row)
    assert NEW_TEXT in next(v for v in row_values if v.field == 2).value

    original = {o.path_id: o.get_raw_data() for o in env.objects}
    tree['m_Script'] = patched.decode('utf-8', 'surrogateescape')
    text.save_typetree(tree)
    result = env.file.save()
    reread = UnityPy.load(result)
    for o in reread.objects:
        if o.path_id != text.path_id:
            assert o.get_raw_data() == original[o.path_id]
    raw = next(o.read_typetree()['m_Script'] for o in reread.objects if o.path_id == text.path_id)
    assert raw.encode('utf-8', 'surrogateescape') == patched

    output.mkdir(parents=True, exist_ok=True)
    target_file = output / external
    target_file.write_bytes(result)
    (output / 'patches.json').write_text(
        json.dumps({f'assets/bin/Data/{external}': str(target_file.resolve())}, indent=2), encoding='utf-8')
    audit = {'source_sha256': hashlib.sha256(source).hexdigest(), 'external': external,
             'language_key': LANG_KEY, 'old': OLD_TEXT.decode(), 'new': NEW_TEXT.decode(),
             'source_size': len(encrypted), 'patched_size': len(patched)}
    (output / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    print('language', LANG_KEY, '4500 -> 3500; length and RSA prefix unchanged')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    patch(args.apk, args.output)
