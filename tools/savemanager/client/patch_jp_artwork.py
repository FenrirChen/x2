"""Apply user-supplied Japanese artwork assets to an existing patched APK.

Only replace matching serialized Unity assets. Preserve source bytes exactly,
validate object identities and local texture references, and never execute or
modify anything in the input directory. APK rebuild and signing are separate.
"""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT.parent / '.phase2_deps'))
import UnityPy


def sha(data):
    return hashlib.sha256(data).hexdigest()


def serialized(data):
    env = UnityPy.load(data)
    assert len(env.files) == 1
    return next(iter(env.files.values()))


def patch(apk, source, output):
    files = sorted(p for p in source.rglob('*') if p.is_file() and re.fullmatch('[0-9a-f]{32}', p.name))
    assert len(files) == 10, f'Expected the supplied ten assets, got {len(files)}'
    assert len({p.name for p in files}) == len(files), 'Duplicate asset names'
    output.mkdir(parents=True, exist_ok=True)
    manifest = {}
    audit = []
    with zipfile.ZipFile(apk) as archive:
        for file in files:
            entry = 'assets/bin/Data/' + file.name
            original = archive.read(entry)  # Adding unknown assets is not allowed.
            replacement = file.read_bytes()
            old, new = serialized(original), serialized(replacement)
            assert old.unity_version == new.unity_version, entry
            assert set(old.objects) == set(new.objects), entry
            assert not new.externals, f'Unexpected external dependency: {entry}'
            textures = []
            sprites = []
            for pid, obj in new.objects.items():
                previous = old.objects[pid]
                assert obj.type.name == previous.type.name, (entry, pid)
                assert obj.type.name in ('Texture2D', 'Sprite'), (entry, pid)
                value, prior = obj.read(), previous.read()
                assert value.m_Name == prior.m_Name, (entry, pid)
                if obj.type.name == 'Texture2D':
                    assert (value.m_Width, value.m_Height, value.m_TextureFormat) == (prior.m_Width, prior.m_Height, prior.m_TextureFormat), entry
                    assert not value.m_StreamData.path, entry
                    pixels = value.image
                    assert pixels.size == (value.m_Width, value.m_Height), entry
                    textures.append({'pid': pid, 'name': value.m_Name, 'dimensions': list(pixels.size), 'format': value.m_TextureFormat})
                else:
                    pointer = value.m_RD.texture
                    assert pointer.m_FileID == 0 and pointer.m_PathID in new.objects, entry
                    assert new.objects[pointer.m_PathID].type.name == 'Texture2D', entry
                    value.image  # Decode with the source Sprite crop/mesh metadata.
                    sprites.append({'pid': pid, 'name': value.m_Name, 'texture_pid': pointer.m_PathID})
            target = output / file.name
            target.write_bytes(replacement)
            assert sha(target.read_bytes()) == sha(replacement)
            manifest[entry] = str(target.resolve())
            audit.append({'entry': entry, 'source': str(file.resolve()), 'bytes': len(replacement),
                          'source_sha256': sha(replacement), 'previous_sha256': sha(original),
                          'changed': original != replacement, 'textures': textures, 'sprites': sprites,
                          'unity_version': str(new.unity_version), 'object_ids_preserved': True})
        (output / 'libil2cpp.so').write_bytes(archive.read('lib/arm64-v8a/libil2cpp.so'))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf8')
    result = {'baseline': str(apk.resolve()), 'source': str(source.resolve()),
              'assets': audit, 'changed': sum(item['changed'] for item in audit),
              'already_present': sum(not item['changed'] for item in audit)}
    (output / 'audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps({'assets': len(audit), 'changed': result['changed'], 'already_present': result['already_present']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('apk', type=Path)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    patch(args.apk, args.source, args.output)
