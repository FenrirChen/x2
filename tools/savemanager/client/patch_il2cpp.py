"""Patch the login-page visitor button to launch the save-manager bridge.

Entry hook: LoginPage.OnMBtnVisitorLoginClick at RVA 0x15166F0 (arm64
libil2cpp.so). Its first instruction is displaced into a code cave; the hook
branches there. The cave dlopen()s libx2save.so, resolves
x2_open_save_manager, and calls it with (this, il2cpp_handle). Bridge returned
The click never falls back to guest login: save-manager failures must not
attempt to authenticate as an unrelated guest account.

PC-relative instructions (b/bl/cbz/cbnz/adrp/add-imm) are encoded manually and
everything is re-verified with an independent capstone disassembly.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

IL2CPP_ENTRY_HOOK = 0x15166F0
CAVE = 0x42B02C0
CAVE_SIZE = 512
PLT_DLOPEN = 0x113E820
PLT_DLSYM = 0x113FA80

ORIGINAL_BYTES = bytes.fromhex("f44fbea9")  # stp x20, x19, [sp, #-0x20]!

STR_LIB = CAVE + 0x100       # "libx2save.so"
STR_SYM = CAVE + 0x120       # "x2_open_save_manager"


def b(pc: int, target: int) -> int:
    return 0x14000000 | (((target - pc) >> 2) & 0x03FFFFFF)


def bl(pc: int, target: int) -> int:
    return 0x94000000 | (((target - pc) >> 2) & 0x03FFFFFF)


def cbz(rt: int, pc: int, target: int) -> int:
    return 0xB4000000 | ((((target - pc) >> 2) & 0x7FFFF) << 5) | rt


def cbnz(rt: int, pc: int, target: int) -> int:
    return 0xB5000000 | ((((target - pc) >> 2) & 0x7FFFF) << 5) | rt


def adrp(rd: int, pc: int, target: int) -> int:
    imm = (target >> 12) - (pc >> 12)
    immlo = imm & 3
    immhi = (imm >> 2) & 0x7FFFF
    return 0x90000000 | (immlo << 29) | (immhi << 5) | rd


def add_imm(rd: int, rn: int, imm: int) -> int:
    return 0x91000000 | ((imm & 0xFFF) << 10) | (rn << 5) | rd


def mov_reg(rd: int, rm: int) -> int:
    return 0xAA0003E0 | (rm << 16) | rd


def build_cave() -> bytes:
    """Cave word list; each entry is (word | None, keystone_mnemonic)."""
    labels = {}

    def at(offset):
        return CAVE + offset

    plan = [
        # displaced instructions copied verbatim from the audited entry
        (lambda pc: 0xA9BE4FF4, "disp stp x20,x19"),
        (lambda pc: 0xA9017BFD, "disp stp x29,x30"),
        (lambda pc: mov_reg(19, 0), "mov x19, x0"),
        (lambda pc: adrp(0, pc, STR_LIB), "adrp lib"),
        (lambda pc: add_imm(0, 0, STR_LIB & 0xFFF), "add lib"),
        (lambda pc: 0x52800021, "mov w1, #1"),                # RTLD_LAZY
        (lambda pc: bl(pc, PLT_DLOPEN), "bl dlopen"),
        (lambda pc: None, "cbz x0"),                          # needs labels; patched below
        (lambda pc: mov_reg(20, 0), "mov x20, x0"),
        (lambda pc: adrp(0, pc, STR_SYM), "adrp sym"),
        (lambda pc: add_imm(0, 0, STR_SYM & 0xFFF), "add sym"),
        (lambda pc: mov_reg(1, 0), "mov x1, x0 (symbol)"),
        (lambda pc: mov_reg(0, 20), "mov x0, x20 (handle)"),
        (lambda pc: bl(pc, PLT_DLSYM), "bl dlsym"),
        (lambda pc: mov_reg(1, 20), "mov x1, x20"),
        (lambda pc: mov_reg(2, 0), "mov x2, x0"),
        (lambda pc: mov_reg(0, 19), "mov x0, x19"),
        (lambda pc: None, "cbz x2"),                          # patched below
        (lambda pc: 0xD63F0040, "blr x2"),
        (lambda pc: None, "cbnz x0"),                         # patched below
    ]
    words = []
    for builder, _desc in plan:
        pc = at(len(words) * 4)
        word = builder(pc)
        words.append(word)

    # resolve label targets
    cbz_x0_idx = 7
    cbz_x2_idx = 17
    cbnz_x0_idx = 19
    handled_idx = 20
    words[cbz_x0_idx] = cbz(0, at(cbz_x0_idx * 4), at(handled_idx * 4))
    words[cbz_x2_idx] = cbz(2, at(cbz_x2_idx * 4), at(handled_idx * 4))
    words[cbnz_x0_idx] = cbnz(0, at(cbnz_x0_idx * 4), at(handled_idx * 4))

    tail = [
        (lambda pc: 0xA9417BFD, "handled ldp x29,x30"),
        (lambda pc: 0xA8C24FF4, "handled ldp x20,x19"),               # 22
        (lambda pc: 0xD65F03C0, "ret"),                               # 23
    ]
    for index, (builder, _desc) in enumerate(tail):
        pc = at((20 + index) * 4)
        words.append(builder(pc))

    blob = b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in words)
    blob = blob.ljust(STR_LIB - CAVE, b"\x00")
    blob += b"libx2save.so\x00"
    blob = blob.ljust(STR_SYM - CAVE, b"\x00")
    blob += b"x2_open_save_manager\x00"
    return blob


def verify(patched: bytes) -> None:
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    print("--- entry hook ---")
    for ins in md.disasm(patched[IL2CPP_ENTRY_HOOK:IL2CPP_ENTRY_HOOK + 4], IL2CPP_ENTRY_HOOK):
        print(f"0x{ins.address:x}: {ins.mnemonic}\t{ins.op_str}")
    print("--- cave ---")
    end = STR_SYM + len(b"x2_open_save_manager\x00")
    for ins in md.disasm(patched[CAVE:CAVE + 24 * 4], CAVE):
        print(f"0x{ins.address:x}: {ins.mnemonic}\t{ins.op_str}")
    print("--- strings ---")
    lib = patched[STR_LIB:STR_LIB + 16].split(b"\x00")[0].decode()
    sym = patched[STR_SYM:STR_SYM + 24].split(b"\x00")[0].decode()
    print(f"lib={lib!r} sym={sym!r}")
    assert lib == "libx2save.so" and sym == "x2_open_save_manager"
    # dlsym(handle, symbol): independently verify register setup and target.
    instructions = list(md.disasm(patched[CAVE:CAVE + 23 * 4], CAVE))
    assert instructions[11].mnemonic == "mov" and instructions[11].op_str == "x1, x0"
    assert instructions[12].mnemonic == "mov" and instructions[12].op_str == "x0, x20"
    assert instructions[13].mnemonic == "bl" and instructions[13].op_str == hex(PLT_DLSYM).replace('0x', '#0x')
    assert instructions[-1].mnemonic == "ret"
    assert not any(op.mnemonic == "b" and op.op_str == f"#0x{IL2CPP_ENTRY_HOOK + 8:x}"
                   for op in instructions), "save-manager must not fall back to guest login"


def patch(data: bytes) -> bytes:
    if data[IL2CPP_ENTRY_HOOK:IL2CPP_ENTRY_HOOK + 4] != ORIGINAL_BYTES:
        raise SystemExit("entry hook bytes do not match the audited baseline")
    if any(data[CAVE:CAVE + CAVE_SIZE]):
        raise SystemExit("code cave is not zero-filled")

    cave_blob = build_cave()
    if len(cave_blob) > CAVE_SIZE:
        raise SystemExit("cave blob exceeds reserved space")
    hook = struct.pack("<I", b(IL2CPP_ENTRY_HOOK, CAVE))

    patched = bytearray(data)
    patched[IL2CPP_ENTRY_HOOK:IL2CPP_ENTRY_HOOK + 4] = hook
    patched[CAVE:CAVE + len(cave_blob)] = cave_blob
    verify(bytes(patched))
    return bytes(patched)


def main() -> None:
    src = sys.argv[1]
    dst = sys.argv[2]
    data = open(src, "rb").read()
    open(dst, "wb").write(patch(data))
    print(f"patched {src} -> {dst}")


if __name__ == "__main__":
    main()
