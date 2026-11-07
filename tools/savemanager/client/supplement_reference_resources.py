"""Migrate visual references only; retain the release's code, URLs and UI logic.

ZIP32 output may exceed 2 GiB, but must remain below ZIP32's 4 GiB boundary.
The raw compressed baseline streams are copied without decompressing/rebuilding
unrelated entries. Sign separately with the existing release identity.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT.parent / '.phase2_deps'))
import UnityPy

DATA = 'assets/bin/Data/'


def load(z, name):
    return next(iter(UnityPy.load(z.read(name)).files.values()))


def external(sf, other, fid):
    if not fid:
        return 0
    item = other.externals[fid - 1]
    for index, prior in enumerate(sf.externals, 1):
        if prior.path == item.path:
            return index
    sf.externals.append(copy.copy(item))
    return len(sf.externals)


def prepare(baseline, donor, output):
    output.mkdir(parents=True, exist_ok=True)
    patches, additions, audit = {}, {}, []
    with zipfile.ZipFile(baseline) as old, zipfile.ZipFile(donor) as new:
        prior = {i.filename: i for i in old.infolist()}
        extra = {n for n in new.namelist() if n not in prior and
                 (n.startswith(DATA) or n.startswith('assets/Video/'))}
        assert all('..' not in Path(n).parts for n in extra)
        # Only Unity resources and streaming videos, never third-party code.
        for name in sorted(extra):
            dest = output / 'added' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(new.read(name))
            additions[name] = str(dest.resolve())
        cache = {}

        def valid_sprite(sf, fid, pid):
            if not pid:
                return False
            if not fid:
                return pid in sf.objects and sf.objects[pid].type.name == 'Sprite'
            name = DATA + sf.externals[fid - 1].path
            if name not in new.namelist():
                return False
            if name not in cache:
                cache[name] = {o.path_id: o.type.name for o in load(new, name).objects.values()}
            return cache[name].get(pid) == 'Sprite'

        for info in new.infolist():
            name = info.filename
            if (not name.startswith(DATA) or name not in prior or
                    info.CRC == prior[name].CRC or name.endswith('globalgamemanagers')):
                continue
            try:
                sf, source = load(old, name), load(new, name)
            except Exception:
                continue  # Encrypted/static tables are outside the visual scope.
            original = {pid: o.get_raw_data() for pid, o in sf.objects.items()}
            changed, rects = set(), set()
            for pid, obj in sf.objects.items():
                other = source.objects.get(pid)
                if obj.type.name != 'MonoBehaviour' or other is None:
                    continue
                raw, desired = obj.get_raw_data(), other.get_raw_data()
                if (len(raw) != 292 or len(desired) != 292 or
                        struct.unpack_from('<ii', raw, 64) != (0, 123) or
                        struct.unpack_from('<ii', desired, 64) != (0, 123)):
                    continue
                fid, sprite = struct.unpack_from('<iq', desired, 196)
                if not valid_sprite(source, fid, sprite):
                    continue
                before_id, before_sprite = struct.unpack_from('<iq', raw, 196)
                before_path = sf.externals[before_id-1].path if before_id else ''
                after_path = source.externals[fid-1].path if fid else ''
                if (before_path, before_sprite) == (after_path, sprite):
                    continue
                # Preserve populated local fixes unless this is a restored asset.
                if before_sprite and DATA + after_path not in extra:
                    continue
                go = struct.unpack_from('<q', raw, 4)[0]
                assert go == struct.unpack_from('<q', desired, 4)[0], (name, pid)
                out = bytearray(raw)
                struct.pack_into('<iq', out, 196, external(sf, source, fid), sprite)
                obj.set_raw_data(bytes(out))
                changed.add(pid)
                rects.add(go)
                audit.append({'file': name, 'image': pid, 'sprite_file': after_path,
                              'sprite_id': sprite, 'was_null': not before_sprite})
            for pid, obj in sf.objects.items():
                if obj.type.name != 'RectTransform' or pid not in source.objects:
                    continue
                tree = obj.read_typetree()
                if tree['m_GameObject']['m_PathID'] not in rects:
                    continue
                target = source.objects[pid].read_typetree()
                for field in ('m_AnchorMin', 'm_AnchorMax', 'm_AnchoredPosition', 'm_SizeDelta', 'm_Pivot'):
                    tree[field] = target[field]
                obj.save_typetree(tree)
                changed.add(pid)
            # Restore the existing AVPro display now that its missing loop exists.
            if name == DATA + '2edc795102e2597479e3e077aac50714':
                for pid, enabled in ((326, 1), (387, 0)):
                    raw = bytearray(sf.objects[pid].get_raw_data())
                    raw[12] = enabled
                    sf.objects[pid].set_raw_data(bytes(raw))
                    changed.add(pid)
            if not changed:
                continue
            payload = sf.save()
            reread = next(iter(UnityPy.load(payload).files.values()))
            assert set(reread.objects) == set(original)
            assert all(reread.objects[pid].get_raw_data() == raw
                       for pid, raw in original.items() if pid not in changed), name
            dest = output / Path(name).name
            dest.write_bytes(payload)
            patches[name] = str(dest.resolve())
        # Merge resource bindings by normalized target, preserving local URLs,
        # season identity and every unrelated Player/Quality/Build setting.
        name = DATA + 'globalgamemanagers'
        sf, source = load(old, name), load(new, name)
        tree, donor_tree = sf.objects[13].read_typetree(), source.objects[13].read_typetree()
        original = {pid: o.get_raw_data() for pid, o in sf.objects.items()}
        def key(other, path, ptr):
            return (path, other.externals[ptr['m_FileID']-1].path if ptr['m_FileID'] else '', ptr['m_PathID'])
        groups = {}
        for path, ptr in donor_tree['m_Container']:
            groups.setdefault(path, []).append(ptr)
        replace = {path for path, pointers in groups.items()
                   if all(DATA + key(source, path, p)[1] in extra for p in pointers)}
        tree['m_Container'] = [(path, ptr) for path, ptr in tree['m_Container'] if path not in replace]
        known = {key(sf, path, ptr) for path, ptr in tree['m_Container']}
        bindings = []
        for path, ptr in donor_tree['m_Container']:
            normalized = key(source, path, ptr)
            if normalized in known or DATA + normalized[1] not in extra:
                continue
            value = dict(ptr, m_FileID=external(sf, source, ptr['m_FileID']))
            tree['m_Container'].append((path, value))
            known.add(normalized)
            bindings.append(normalized)
        sf.objects[13].save_typetree(tree)
        payload = sf.save()
        reread = next(iter(UnityPy.load(payload).files.values()))
        assert all(reread.objects[pid].get_raw_data() == raw for pid, raw in original.items() if pid != 13)
        dest = output / 'globalgamemanagers'
        dest.write_bytes(payload)
        patches[name] = str(dest.resolve())
    manifest = {'patches': patches, 'additions': additions, 'baseline': str(baseline),
                'donor': str(donor), 'images': audit, 'resource_bindings': bindings}
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print('PREPARED', len(patches), 'patched files', len(additions), 'new files', len(audit), 'image refs', flush=True)


def assemble(baseline, manifest, output):
    plan = json.loads(manifest.read_text(encoding='utf-8'))
    patched, additions = plan['patches'], plan['additions']
    records = []
    with zipfile.ZipFile(baseline) as z, Path(baseline).open('rb') as src, output.open('wb') as dst:
        assert not (set(additions) & set(z.namelist())), 'added entry already exists'
        for info in list(z.infolist()) + [zipfile.ZipInfo(n) for n in additions]:
            name = info.filename
            if name.startswith('META-INF/'):
                continue
            if name in patched or name in additions:
                payload = Path(patched.get(name) or additions[name]).read_bytes()
                crc, usize = zlib.crc32(payload) & 0xffffffff, len(payload)
                method = 0 if name.startswith('assets/Video/') else 8
                if method == 8:
                    c = zlib.compressobj(6, zlib.DEFLATED, -15)
                    data = c.compress(payload) + c.flush()
                else:
                    data = payload
                csize = len(data)
            else:
                crc, usize, method, csize = info.CRC, info.file_size, info.compress_type, info.compress_size
                src.seek(info.header_offset)
                hdr = src.read(30)
                nl, el = struct.unpack_from('<HH', hdr, 26)
                src.seek(nl + el, 1)
                data = None
            encoded = name.encode('utf-8')
            offset = dst.tell()
            pad = (-(offset + 30 + len(encoded))) % 4 if method == 0 else 0
            extra = struct.pack('<HH', 0, pad) + bytes(pad) if pad else b''
            flags = 0x800
            dst.write(struct.pack('<IHHHHHIIIHH', 0x04034b50, 20, flags, method, 0, 33,
                                  crc, csize, usize, len(encoded), len(extra)))
            dst.write(encoded)
            dst.write(extra)
            if data is not None:
                dst.write(data)
            else:
                remaining = csize
                while remaining:
                    chunk = src.read(min(4 << 20, remaining))
                    if not chunk:
                        raise EOFError(name)
                    dst.write(chunk)
                    remaining -= len(chunk)
            records.append((encoded, flags, method, crc, csize, usize, offset))
        cd = dst.tell()
        for n, flags, method, crc, cs, us, offset in records:
            assert max(cs, us, offset) < 0xffffffff
            dst.write(struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 20, 20, flags, method,
                                  0, 33, crc, cs, us, len(n), 0, 0, 0, 0, 0, offset))
            dst.write(n)
        cd_size = dst.tell() - cd
        assert dst.tell() < 0xffffffff and len(records) < 65535
        dst.write(struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, len(records), len(records), cd_size, cd, 0))
    print('BUILT', str(output), output.stat().st_size, flush=True)


def validate(baseline, manifest, apk, report):
    plan = json.loads(manifest.read_text(encoding='utf-8'))
    expected = {**plan['patches'], **plan['additions']}
    with zipfile.ZipFile(baseline) as a, zipfile.ZipFile(apk) as b:
        old = {i.filename: i for i in a.infolist() if not i.filename.startswith('META-INF/')}
        new = {i.filename: i for i in b.infolist() if not i.filename.startswith('META-INF/')}
        assert len(b.infolist()) == len(set(b.namelist())), 'duplicate ZIP entries'
        assert set(new) == set(old) | set(plan['additions'])
        for n, info in old.items():
            if n not in expected:
                assert (info.CRC, info.file_size) == (new[n].CRC, new[n].file_size), n
        for n, path in expected.items():
            assert hashlib.sha256(b.read(n)).digest() == hashlib.sha256(Path(path).read_bytes()).digest(), n
        resolved = {}
        for row in plan['images']:
            name = row['file']
            if name not in resolved:
                resolved[name] = load(b, name)
            obj = resolved[name].objects[row['image']]
            fid, pid = struct.unpack_from('<iq', obj.get_raw_data(), 196)
            target = DATA + resolved[name].externals[fid-1].path if fid else name
            if target not in resolved:
                resolved[target] = load(b, target)
            assert resolved[target].objects[pid].type.name == 'Sprite', row
        for row in plan['additions']:
            if row.startswith('assets/Video/'):
                assert b.getinfo(row).compress_type == 0, row
        for n in ('lib/arm64-v8a/libil2cpp.so', 'lib/arm64-v8a/libunity.so', 'classes5.dex',
                  'lib/arm64-v8a/libx2save.so', 'assets/42c44a368fc3544296d1e717a485b306.ab'):
            assert b.read(n) == a.read(n), n
        with apk.open('rb') as f:
            for i in b.infolist():
                if i.compress_type != 0:
                    continue
                f.seek(i.header_offset)
                nl, el = struct.unpack_from('<HH', f.read(30), 26)
                assert (i.header_offset + 30 + nl + el) % 4 == 0, i.filename
        assert b.testzip() is None
    h = hashlib.sha256()
    with apk.open('rb') as f:
        for chunk in iter(lambda: f.read(4 << 20), b''):
            h.update(chunk)
    result = {'apk': str(apk), 'bytes': apk.stat().st_size, 'sha256': h.hexdigest(),
              'full_crc': 'passed', 'code_config_preserved': True, 'stored_alignment': 4,
              'modified_files': len(plan['patches']), 'added_files': len(plan['additions'])}
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'build', 'validate'))
    p.add_argument('baseline', type=Path)
    p.add_argument('input', type=Path, help='donor APK for prepare; manifest for build/validate')
    p.add_argument('output', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    if a.mode == 'prepare':
        prepare(a.baseline, a.input, a.output)
    elif a.mode == 'build':
        assemble(a.baseline, a.input, a.output)
    else:
        validate(a.baseline, a.input, a.output, a.report)
