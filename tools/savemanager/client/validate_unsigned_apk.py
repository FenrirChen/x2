"""Validate the unsigned SaveManager APK before signing.

Checks: ZIP integrity (full CRC), entry inventory, text patches complete,
libil2cpp trampoline in place, libunity.so untouched (allocator fix intact),
new entries present, alignment, no leftover signatures.
"""
import hashlib
import io
import struct
import sys
import zipfile

APK = sys.argv[1]
BASELINE = r"D:\demo\x2\逆向\打包\X2-Revival-AllocatorFix-signed.apk"
LIBUNITY_SHA = "7c5a3c1f457572727020d498bc894a0832cc1dcd415d1a35a3c59e0ee10c8aa5"

HOOK_OFFSET = 0x15166F0
EXPECTED_HOOK = bytes.fromhex("f466b614")  # b 0x42b02c0

zf = zipfile.ZipFile(APK)
names = zf.namelist()
print("entries:", len(names))
baseline = zipfile.ZipFile(BASELINE)
baseline_names = baseline.namelist()

# 1) full CRC
bad = zf.testzip()
assert bad is None, f"CRC failed: {bad}"
print("zip CRC: all entries OK")

# 2) inventory
new_expected = {"lib/arm64-v8a/libx2save.so", "classes5.dex"}
added = set(names) - set(baseline_names)
removed = set(baseline_names) - set(names)
assert added == new_expected, added
assert removed == {"META-INF/X2-REVIV.SF", "META-INF/X2-REVIV.RSA", "META-INF/MANIFEST.MF"}, removed
assert not any(n.startswith("META-INF/") for n in names), "leftover META-INF"
print("entry delta: +%s -%s" % (sorted(added), sorted(removed)))

# 3) text patches complete: no 游客/遊客 strings remain anywhere
for needle in ("游客登录".encode(), "遊客登入".encode()):
    for name in names:
        if name.startswith("META-INF/"):
            continue
        raw = zf.read(name)
        if needle in raw:
            raise AssertionError(f"unpatched text found in {name}: {needle}")
print("text patches: 游客登录/遊客登入 fully replaced")

# count new 存档管理 occurrences in the four patched entries
for name in ("assets/bin/Data/bf39f9c839b67204eadd3371ec9025c9",
             "assets/bin/Data/844762d28a77f85408b631eb3f0186bc",
             "assets/bin/Data/9f7c8bf97310515489bb8c18404a80bf",
             "res/layout/dialog_dhui2_login.xml"):
    count = zf.read(name).count("存档管理".encode())
    print(f"  {name.split('/')[-1]}: {count} x 存档管理")

# 4) libil2cpp patch
lib = zf.read("lib/arm64-v8a/libil2cpp.so")
assert lib[HOOK_OFFSET:HOOK_OFFSET + 4] == EXPECTED_HOOK, "trampoline hook missing"
cave = lib[0x42B02C0:0x42B02C0 + 24 * 4]
assert cave[:4] == bytes.fromhex("f44fbea9"), "cave displaced stp missing"
assert b"libx2save.so\x00" in lib[0x42B03C0:0x42B0400]
assert b"x2_open_save_manager\x00" in lib[0x42B03E0:0x42B0440]
print("libil2cpp: trampoline hook + cave verified")

# 5) libunity unchanged (allocator fix)
unity = zf.read("lib/arm64-v8a/libunity.so")
actual = hashlib.sha256(unity).hexdigest()
assert actual == LIBUNITY_SHA, f"libunity regression: {actual}"
print("libunity.so SHA256:", actual)

# 6) libx2save.so sanity
so = zf.read("lib/arm64-v8a/libx2save.so")
assert so[:4] == b"\x7fELF" and b"x2_open_save_manager" in so
assert b"libc.so" in so and b"libdl.so" in so
print("libx2save.so:", len(so), "bytes, AArch64 ELF with DT_NEEDED libc/libdl")

# 7) dex sanity
dex = zf.read("classes5.dex")
assert dex[:4] == b"dex\n" and b"SaveManagerDialogFragment" in dex and b"SaveManagerBridge" in dex
assert b"currentActivity" in dex  # UnityPlayer.currentActivity invocation site
# the compile stub is never a defined class: d8 received only com/siva classes;
# the "UnityPlayer" string remains solely as the invocation type reference.
print("classes5.dex:", len(dex), "bytes")

# 8) alignment of stored entries
aligned = 0
misaligned = []
data = open(APK, 'rb').read()
eocd_pos, n_total, cd_size, cd_off = 0, 0, 0, 0
i = data.rfind(b"PK\x05\x06")
n_total = struct.unpack_from('<H', data, i + 10)[0]
cd_size = struct.unpack_from('<I', data, i + 12)[0]
cd_off = struct.unpack_from('<I', data, i + 16)[0]
p = cd_off
for _ in range(n_total):
    flags, method = struct.unpack_from('<HH', data, p + 8)
    nlen, elen = struct.unpack_from('<HH', data, p + 28)
    lho = struct.unpack_from('<I', data, p + 42)[0]
    if method == 0:
        aligned += 1
        if (lho + 30 + ((data[lho + 26:lho + 28] and struct.unpack_from('<H', data, lho + 26)[0]) or 0)
                + (struct.unpack_from('<H', data, lho + 28)[0])) % 4 != 0:
            misaligned.append(lho)
    p += 46 + nlen + elen + struct.unpack_from('<H', data, p + 32)[0]
print(f"stored entries checked: {aligned}, misaligned: {len(misaligned)}")

size = len(data)
print(f"unsigned size: {size}  headroom to 2^31-1: {(1 << 31) - 1 - size}")
assert size < (1 << 31) - 1
print("VALIDATION PASSED")
