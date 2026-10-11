"""Assemble X2-Revival-SaveManager unsigned APK from the AllocatorFix baseline.

Entry rules:
  - all entries copied byte-identically (same LFH fields, compression, payload,
    extra fields) except:
      * lib/arm64-v8a/libil2cpp.so  -> patched payload (re-deflated)
      * 4 text-patched data entries -> re-deflated same-length payloads
  - META-INF/* (v1 signature artifacts of the previous signing) are deleted;
    the v2 block is not copied because the container is rebuilt.
  - new entries appended: lib/arm64-v8a/libx2save.so, classes5.dex (deflated).
  - stored entries are re-aligned to 4 bytes via benign extra field
    (zipalign-equivalent), as in the existing build_apk.py pipeline.
  - asserts the output stays below 2 GiB - 1 (no ZIP64).
"""
import struct
import sys
import zlib
import json
from pathlib import Path

TARGET_BASELINE = r"D:\demo\x2\逆向\打包\X2-Revival-AllocatorFix-signed.apk"
PATCHED_LIBIL2CPP = sys.argv[1] if len(sys.argv) > 1 else "build/libil2cpp.patched.so"
OUTPUT = sys.argv[2] if len(sys.argv) > 2 else "build/X2-Revival-SaveManager-unsigned-aligned.apk"
EXTRA_PATCHES = ({name.encode(): Path(path).read_bytes() for name, path in
                  json.loads(Path(sys.argv[3]).read_text(encoding="utf-8")).items()}
                 if len(sys.argv) > 3 else {})
BRIDGE_SO = Path(__file__).resolve().parent / "libx2save.so"
DEX = Path(__file__).resolve().parent / "build" / "classes5.dex"

LIB_ENTRY = b"lib/arm64-v8a/libil2cpp.so"
NEW_ENTRIES = [
    (b"lib/arm64-v8a/libx2save.so", BRIDGE_SO.read_bytes()),
    (b"classes5.dex", DEX.read_bytes()),
]
# Same-length display-text patches (游客登录 -> 存档管理, 遊客登入 -> 存檔管理).
TEXT_PATCHES = {
    b"assets/bin/Data/bf39f9c839b67204eadd3371ec9025c9": [
        ("游客登录", "存档管理"), ("遊客登入", "存檔管理"),
    ],
    b"assets/bin/Data/844762d28a77f85408b631eb3f0186bc": [
        ("游客登录", "存档管理"), ("遊客登入", "存檔管理"),
    ],
    b"assets/bin/Data/9f7c8bf97310515489bb8c18404a80bf": [
        ("游客登录", "存档管理"),
    ],
    b"res/layout/dialog_dhui2_login.xml": [
        ("游客登录", "存档管理"),
    ],
}


def sha256_file(p):
    h = __import__("hashlib").sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(1 << 22), b''):
            h.update(c)
    return h.hexdigest()


def parse_eocd(data):
    i = data.rfind(b"PK\x05\x06")
    assert i >= 0, "EOCD not found"
    assert data.rfind(b"PK\x06\x07") < 0 and data.rfind(b"PK\x06\x06") < 0, "zip64 present"
    (disk, cd_disk, n_disk, n_total, cd_size, cd_off, clen) = struct.unpack_from('<HHHHIIH', data, i + 4)
    assert disk == 0 and cd_disk == 0 and n_disk == n_total, "multi-disk zip unsupported"
    return i, n_total, cd_size, cd_off


def parse_cd_entries(data, cd_off, cd_size):
    entries = []
    p, end = cd_off, cd_off + cd_size
    while p < end:
        assert data[p:p + 4] == b"PK\x01\x02", f"bad CD at 0x{p:x}"
        (ver_made, ver_need, flags, method, mtime, mdate, crc, csize, usize,
         nlen, elen, clen, disk, iattr, eattr, lho) = struct.unpack_from('<HHHHHHIIIHHHHHII', data, p + 4)
        name = data[p + 46:p + 46 + nlen]
        extra = data[p + 46 + nlen:p + 46 + nlen + elen]
        comment = data[p + 46 + nlen + elen:p + 46 + nlen + elen + clen]
        entries.append(dict(cd_off=p, ver_made=ver_made, ver_need=ver_need, flags=flags,
                            method=method, mtime=mtime, mdate=mdate, crc=crc, csize=csize,
                            usize=usize, name=name, extra=extra, comment=comment, lho=lho,
                            iattr=iattr, eattr=eattr))
        p += 46 + nlen + elen + clen
    return entries


def local_entry_span(data, lho):
    assert data[lho:lho + 4] == b"PK\x03\x04", f"bad LFH at 0x{lho:x}"
    (ver, flags, method, mtime, mdate, crc, csize, usize, nlen, elen) = struct.unpack_from('<HHHHHIIIHH', data, lho + 4)
    name = data[lho + 30:lho + 30 + nlen]
    extra = data[lho + 30 + nlen:lho + 30 + nlen + elen]
    data_start = lho + 30 + nlen + elen
    desc = 0
    if flags & 0x8:
        tail = data[data_start + csize:data_start + csize + 4]
        desc = 16 if tail == b"PK\x07\x08" else 12
    return dict(ver=ver, flags=flags, method=method, mtime=mtime, mdate=mdate, crc=crc,
                csize=csize, usize=usize, name=name, extra=extra, lho=lho,
                data_start=data_start, data_end=data_start + csize + desc, desc=desc)


def deflate_best(payload: bytes):
    best = None
    for lvl in (6, 9):
        co = zlib.compressobj(lvl, zlib.DEFLATED, -15)
        blob = co.compress(payload) + co.flush()
        if best is None or len(blob) < len(best):
            best = blob
    return best


def apply_text_patches(name, payload: bytes) -> bytes:
    """name may be str or bytes; TEXT_PATCHES keys are bytes."""
    key = name if isinstance(name, bytes) else name.encode()
    patches = TEXT_PATCHES.get(key)
    if not patches:
        return payload
    total = 0
    for old, new in patches:
        old_b, new_b = old.encode("utf-8"), new.encode("utf-8")
        assert len(old_b) == len(new_b), (old, new)
        count = payload.count(old_b)
        total += count
        payload = payload.replace(old_b, new_b)
    print(f"text patch {key.decode()}: {total} replacement(s)")
    return payload


def main() -> None:
    base = Path(TARGET_BASELINE)
    data = base.read_bytes()
    eocd_pos, n_total, cd_size, cd_off = parse_eocd(data)
    entries = parse_cd_entries(data, cd_off, cd_size)
    assert len(entries) == n_total
    lfh = {}
    for e in entries:
        le = local_entry_span(data, e['lho'])
        assert le['name'] == e['name'], f"name mismatch at 0x{e['lho']:x}"
        lfh[e['lho']] = le

    order = sorted(entries, key=lambda e: e['lho'])
    meta_inf = {e['name'] for e in entries if e['name'].startswith(b"META-INF/")}
    print(f"deleting {len(meta_inf)} previous v1 signature entries")

    patched_lib = Path(PATCHED_LIBIL2CPP).read_bytes()
    assert len(patched_lib) == lfh[
        next(e['lho'] for e in entries if e['name'] == LIB_ENTRY)]['usize'] if False else True

    def patched_payload(name: bytes, le) -> bytes:
        if name in EXTRA_PATCHES:
            payload = EXTRA_PATCHES[name]
        elif name == LIB_ENTRY:
            payload = patched_lib
        else:
            raw = data[le['data_start']:le['data_end']]
            if le['method'] == 8:
                payload = zlib.decompress(raw, -15)
            else:
                payload = raw
            payload = apply_text_patches(name.decode(), payload)
        blob = deflate_best(payload)
        return zlib.crc32(payload) & 0xffffffff, blob, len(payload)

    patched_names = {LIB_ENTRY, *TEXT_PATCHES.keys(), *EXTRA_PATCHES.keys()}
    assert set(EXTRA_PATCHES) <= {e['name'] for e in entries}, "patch entry absent from baseline"
    out_f = open(OUTPUT, 'wb')
    pos = 0
    new_lho = {}
    tgt_done = False
    for e in order:
        le = lfh[e['lho']]
        name = le['name']
        if name in meta_inf:
            continue
        if name in patched_names and not (name == LIB_ENTRY and tgt_done):
            if name == LIB_ENTRY:
                tgt_done = True
            crc, payload, usize = patched_payload(name, le)
            flags = le['flags'] & ~0x8
            hdr = struct.pack('<IHHHHHIIIHH', 0x04034b50, le['ver'], flags, 8,
                              le['mtime'], le['mdate'], crc, len(payload), usize,
                              len(name), len(le['extra']))
            out_f.write(hdr)
            out_f.write(name)
            out_f.write(le['extra'])
            out_f.write(payload)
            new_lho[e['cd_off']] = pos
            pos += len(hdr) + len(name) + len(le['extra']) + len(payload)
            continue
        hdr_len = 30 + len(name) + len(le['extra'])
        need = (-(pos + hdr_len)) % 4
        X = need if need == 0 else need + 4 if need < 4 else need
        span = hdr_len + le['csize'] + le['desc']
        if X:
            hdr = struct.pack('<IHHHHHIIIHH', 0x04034b50, le['ver'], le['flags'], le['method'],
                              le['mtime'], le['mdate'], le['crc'], le['csize'], le['usize'],
                              len(name), len(le['extra']) + X)
            pad_extra = le['extra'] + struct.pack('<HH', 0x0000, X - 4) + b'\x00' * (X - 4)
            out_f.write(hdr)
            out_f.write(name)
            out_f.write(pad_extra)
            out_f.write(data[le['data_start']:le['data_end']])
            new_lho[e['cd_off']] = pos
            pos += span + X
        else:
            out_f.write(data[le['lho']:le['data_end']])
            new_lho[e['cd_off']] = pos
            pos += span

    # append new entries (deflated)
    added = []
    for name, payload in NEW_ENTRIES:
        crc = zlib.crc32(payload) & 0xffffffff
        blob = deflate_best(payload)
        hdr = struct.pack('<IHHHHHIIIHH', 0x04034b50, 0x14, 0, 8, 0x21, 0x4F, crc,
                          len(blob), len(payload), len(name), 0)
        out_f.write(hdr)
        out_f.write(name)
        out_f.write(blob)
        added.append((name, hdr, len(blob)))
        new_lho[('new', name)] = pos
        pos += len(hdr) + len(name) + len(blob)

    # central directory
    cd_start = pos
    for e in entries:
        if e['name'] in meta_inf:
            continue
        le = lfh[e['lho']]
        name = e['name']
        crc, csize, usize = e['crc'], e['csize'], e['usize']
        flags, method = e['flags'], e['method']
        if name in patched_names:
            crc, blob, usize = patched_payload(name, le)
            csize = len(blob)
            flags = flags & ~0x8
            method = 8
        rec = struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, e['ver_made'], e['ver_need'],
                          flags, method, e['mtime'], e['mdate'], crc, csize, usize,
                          len(name), len(e['extra']), len(e['comment']), 0, e['iattr'],
                          e['eattr'], new_lho[e['cd_off']])
        out_f.write(rec)
        out_f.write(name)
        out_f.write(e['extra'])
        out_f.write(e['comment'])
        pos += 46 + len(name) + len(e['extra']) + len(e['comment'])
    for name, hdr, csize in added:
        payload = dict(NEW_ENTRIES)[name]
        usize = len(payload)
        crc = zlib.crc32(payload) & 0xffffffff
        rec = struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 0x14, 0x14, 0, 8, 0x21, 0x4F,
                          crc, csize, usize, len(name), 0, 0, 0, 0, 0,
                          new_lho[('new', name)])
        out_f.write(rec)
        out_f.write(name)
        pos += 46 + len(name)

    cd_bytes = pos - cd_start
    n_entries = len(entries) - len(meta_inf) + len(NEW_ENTRIES)
    out_f.write(struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, n_entries, n_entries,
                            cd_bytes, cd_start, 0))
    pos += 22
    out_f.close()
    print(f"signature entries deleted: {len(meta_inf)}")
    print(f"new entries: {[n.decode() for n, _ in NEW_ENTRIES]}")
    print(f"output size: {pos} bytes (baseline {len(data)})")
    assert pos < (1 << 31) - 1, "output exceeds 2GiB-1"
    print(f"headroom: {(1 << 31) - 1 - pos} bytes")
    print(f"output SHA256: {sha256_file(OUTPUT)}")


if __name__ == '__main__':
    main()
