"""Bind each retained cafe UI to its own activity's original recipe IDs.

The shared NewYearFood.IsUse flag enables only the latest event. Older UI
pages consequently show latest-event recipes with same-name, different-ID
ingredients. Use audited per-page IDs derived from ActivityParam2 instead.
"""
import argparse
import hashlib
import json
import struct
import zipfile
from pathlib import Path

from patch_activity_ui import branch

ROOT = Path(__file__).resolve().parents[3]
HOOKS = ((10, 0x19F09A8, 0x19F09B4, 0x19F09EC, 0x42B0C00),
         (37, 0x1A2B95C, 0x1A2B968, 0x1A2B9A0, 0x42B0C20))


def recipe_ids(group):
    data = json.loads((ROOT / 'src/x2server/data/activity_rotation_catalog.json').read_text(encoding='utf-8'))
    theme = next(t for t in data['themes'] if t['group'] == group)
    activity = next(a for a in theme['activities'] if a['ActivityType']['value'] == 27)
    return sorted(r['RecipeID'] for r in data['tables']['NewYearFood']
                  if set(r['ItemGroup']).issubset(activity['ActivityParam2']))


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        native = bytearray(archive.read('lib/arm64-v8a/libil2cpp.so'))
    audit = []
    for group, hook, resume, skip, cave in HOOKS:
        ids = recipe_ids(group)
        assert ids == list(range(ids[0], ids[-1] + 1))
        assert native[hook:hook + 8] == bytes.fromhex('e84e40b91f050071')
        # w8 is the predicate temporary; all other registers are preserved.
        # Unsigned subtraction rejects IDs below the first as well as above
        # the last, including absent/zero IDs. Preserve the original loop.
        words = [0xB94012E8, 0x51000108 | (ids[0] << 10),
                 0x7100011F | (len(ids) << 10),
                 0x54000043,  # b.lo to the local resume branch
                 branch(cave + 16, skip), branch(cave + 20, resume)]
        code = struct.pack('<6I', *words)
        assert not any(native[cave:cave + len(code)])
        native[cave:cave + len(code)] = code
        struct.pack_into('<I', native, hook, branch(hook, cave))
        audit.append({'group': group, 'recipe_ids': ids, 'hook': hex(hook),
                      'cave': hex(cave), 'code': code.hex()})
    (output / 'libil2cpp.so').write_bytes(native)
    (output / 'manifest.json').write_text('{}', encoding='utf-8')
    (output / 'audit.json').write_text(json.dumps({
        'baseline': str(apk), 'native_sha256': hashlib.sha256(native).hexdigest(),
        'patches': audit}, indent=2), encoding='utf-8')
    print(json.dumps(audit))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch(args.apk, args.output)
