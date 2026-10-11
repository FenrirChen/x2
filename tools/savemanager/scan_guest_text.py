"""Scan every APK entry (after full decompression, including Unity bundles)
for the UTF-8 string 游客登录 and report where it lives.

Read-only against the baseline APK.
"""
import io
import struct
import sys
import zipfile
import zlib

TARGET = "游客登录".encode("utf-8")
ALT = ("游客登录", "登 录", "游客")

apk = sys.argv[1] if len(sys.argv) > 1 else r"D:\demo\x2\逆向\打包\X2-Revival-AllocatorFix-signed.apk"

zf = zipfile.ZipFile(apk)
names = zf.namelist()
print("entries:", len(names))

hits = []
for name in names:
    if name.endswith("/"):
        continue
    raw = zf.read(name)
    # 1) raw bytes
    if TARGET in raw:
        hits.append((name, "raw", raw.count(TARGET)))
        continue
    # 2) UnityFS bundle? try UnityPy extraction of all text objects
    if raw[:7] == b"UnityFS":
        try:
            import UnityPy
            env = UnityPy.load(io.BytesIO(raw))
            found = 0
            for obj in env.objects:
                try:
                    data = obj.get_raw_data()
                except Exception:
                    continue
                if TARGET in data:
                    found += 1
            if found:
                hits.append((name, "unityfs-object", found))
        except Exception as exc:
            print("bundle fail", name, exc)
    # 3) other zlib streams inside (best-effort scan)
    else:
        # scan for zlib streams
        pos = raw.find(b"\x78\x9c")
        while pos != -1 and pos < len(raw):
            try:
                d = zlib.decompressobj()
                out = d.decompress(raw[pos:])
                if TARGET in out:
                    hits.append((name, f"zlib@0x{pos:x}", out.count(TARGET)))
                    break
            except Exception:
                pass
            pos = raw.find(b"\x78\x9c", pos + 1)

for h in hits:
    print(h)
print("total files with hits:", len(hits))
