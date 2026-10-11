"""Build libx2save.so (aarch64 Android) without an NDK.

zig cc compiles the bridge with musl generic Linux headers (-nostdlib so no
musl runtime is embedded), then lld links two empty stub libraries purely to
record DT_NEEDED libc.so/libdl.so entries, which Android's runtime linker maps
to the real system libraries at load time.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZIG = HERE.parents[3] / ".runtime" / "zig" / "zig.exe"


def zig() -> str:
    return str(ZIG)


def run(cmd):
    print("+", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
        raise SystemExit(f"command failed: {cmd}")
    if result.stdout.strip():
        print(result.stdout.strip())


def main() -> None:
    out = HERE / "libx2save.so"
    target = "aarch64-linux-musl"
    stub_dir = Path(tempfile.mkdtemp(prefix="x2stub_"))
    try:
        for name in ("libc.so", "libdl.so"):
            run([zig(), "cc", "-target", "aarch64-linux-musl", "-shared", "-fPIC", "-nostdlib",
                 "-Wl,-soname", "-Wl," + name,
                 "-o", str(stub_dir / name), str(HERE / "stub.c")])
        run([zig(), "cc", f"-target", "aarch64-linux-musl", "-shared", "-fPIC", "-nostdlib", "-O2",
             "-Wl,-soname", "-Wl,libx2save.so",
             "-o", str(out), str(HERE / "x2save_bridge.c"),
             f"-L{stub_dir}", "-l:libdl.so", "-l:libc.so"])
    finally:
        shutil.rmtree(stub_dir, ignore_errors=True)
    data = out.read_bytes()
    print(f"built {out} ({len(data)} bytes)")
    # quick sanity: AArch64 ELF, exports our entry symbol
    assert data[:4] == b"\x7fELF" and data[4] == 2 and data[5] == 1
    import struct
    assert struct.unpack_from("<H", data, 18)[0] == 183, "not AArch64"
    assert b"x2_open_save_manager" in data
    assert b"libc.so" in data and b"libdl.so" in data


if __name__ == "__main__":
    main()
