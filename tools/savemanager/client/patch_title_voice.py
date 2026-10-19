"""Patch libil2cpp.so so the main hall replays the board hero's 「标题」 voice.

Entry hook: MainHallFSM.MainAniEnter (arm64 libil2cpp.so). Its first
instruction is displaced into a code cave; the cave dlopen()s libx2save.so,
resolves x2_play_login_title_voice, calls it with (this, handle), restores the
caller-saved registers, re-executes the displaced instruction and branches back
to MainAniEnter+4.

That resume branch is the difference from patch_il2cpp.py: the login-button
trampoline replaces its target (it must not fall back to guest login), while
this one *appends* to it - MainAniEnter still has to run, it drives the hall
entrance animation, the BGM switch and the two-second input lock.

Only the hook RVA is per-build (taken from the audited dump.cs / script.json of
the libil2cpp.so being patched); the dlopen/dlsym PLT stubs and the zero code
cave are located in the ELF itself. The result is re-verified with an
independent capstone disassembly: the displaced instructions must be position
independent, the last cave instruction must branch to entry+4, and no byte
outside the hook word and the cave may change.
"""
import struct
import sys

from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

LIB_NAME = "libx2save.so"
SYMBOL = "x2_play_login_title_voice"
CAVE_SIZE = 512
STR_LIB = 0x100                     # string offsets inside the cave blob
STR_SYM = 0x120
STACK_FRAME = 0xA0                  # x0..x15 plus one scratch slot for the handle

# ranges already used by other trampolines of this toolchain; the auto-located
# cave must not overlap them (save-manager's login-button cave).
RESERVED = ((0x42B02C0, 0x42B02C0 + CAVE_SIZE),)

# instruction words copied verbatim by earlier audits; they pin the hand-rolled
# encoders below to something already proven before anything is written out.
KNOWN_STP_OFF = (0xA9017BFD, 29, 30, 31, 0x10)   # stp x29, x30, [sp, #0x10]
KNOWN_LDP_OFF = (0xA9417BFD, 29, 30, 31, 0x10)   # ldp x29, x30, [sp, #0x10]
KNOWN_STP_PRE = (0xA9BF7BFD, 29, 30, 31, -0x10)  # stp x29, x30, [sp, #-0x10]!

# mnemonics that would break if their instruction is relocated
PC_RELATIVE = frozenset(("adr", "adrp", "b", "bl", "br", "blr", "cbz", "cbnz",
                         "tbz", "tbnz", "ret", "prfm"))

STP_OFF_BASE = 0xA9000000
STP_PRE_BASE = 0xA9800000
LDP_OFF_BASE = 0xA9400000


def b(pc: int, target: int) -> int:
    return 0x14000000 | (((target - pc) >> 2) & 0x03FFFFFF)


def bl(pc: int, target: int) -> int:
    return 0x94000000 | (((target - pc) >> 2) & 0x03FFFFFF)


def cbz(rt: int, pc: int, target: int) -> int:
    return 0xB4000000 | ((((target - pc) >> 2) & 0x7FFFF) << 5) | rt


def adrp(rd: int, pc: int, target: int) -> int:
    imm = (target >> 12) - (pc >> 12)
    immlo = imm & 3
    immhi = (imm >> 2) & 0x7FFFF
    return 0x90000000 | (immlo << 29) | (immhi << 5) | rd


def add_imm(rd: int, rn: int, imm: int) -> int:
    return 0x91000000 | ((imm & 0xFFF) << 10) | (rn << 5) | rd


def sub_imm(rd: int, rn: int, imm: int) -> int:
    return 0xD1000000 | ((imm & 0xFFF) << 10) | (rn << 5) | rd


def mov_reg(rd: int, rm: int) -> int:
    return 0xAA0003E0 | (rm << 16) | rd


def blr(rm: int) -> int:
    return 0xD63F0000 | (rm << 5)


def ldr_imm(rt: int, rn: int, offset: int) -> int:
    return 0xF9400000 | (((offset >> 3) & 0xFFF) << 10) | (rn << 5) | rt


def str_imm(rt: int, rn: int, offset: int) -> int:
    return 0xF9000000 | (((offset >> 3) & 0xFFF) << 10) | (rn << 5) | rt


def stp_off(rt: int, rt2: int, rn: int, offset: int) -> int:
    return STP_OFF_BASE | (((offset >> 3) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt


def ldp_off(rt: int, rt2: int, rn: int, offset: int) -> int:
    return LDP_OFF_BASE | (((offset >> 3) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt


def stp_pre(rt: int, rt2: int, rn: int, offset: int) -> int:
    return STP_PRE_BASE | (((offset >> 3) & 0x7F) << 15) | (rt2 << 10) | (rn << 5) | rt


def self_check_encoders() -> None:
    for word, rt, rt2, rn, off, encoder in (
        (*KNOWN_STP_OFF, stp_off), (*KNOWN_LDP_OFF, ldp_off), (*KNOWN_STP_PRE, stp_pre),
    ):
        assert encoder(rt, rt2, rn, off) == word, hex(encoder(rt, rt2, rn, off))


# --------------------------------------------------------------------------
# ELF helpers: PLT stubs and a zero-filled cave inside the executable segment
# --------------------------------------------------------------------------

def parse_elf(b: bytes):
    u16 = lambda o: struct.unpack_from("<H", b, o)[0]
    u32 = lambda o: struct.unpack_from("<I", b, o)[0]
    u64 = lambda o: struct.unpack_from("<Q", b, o)[0]
    assert b[:4] == b"\x7fELF" and b[4] == 2, "not a 64-bit ELF"
    e_phoff, e_shoff = u64(0x20), u64(0x28)
    e_phentsize, e_phnum = u16(0x36), u16(0x38)
    e_shentsize, e_shnum, e_shstrndx = u16(0x3A), u16(0x3C), u16(0x3E)

    phdrs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, p_flags = u32(o), u32(o + 4)
        p_offset, p_vaddr, _pa, p_filesz, p_memsz, p_align = struct.unpack_from("<QQQQQQ", b, o + 8)
        phdrs.append(dict(type=p_type, flags=p_flags, off=p_offset, vaddr=p_vaddr,
                          filesz=p_filesz, memsz=p_memsz))

    def v2o(v):
        for p in phdrs:
            if p["type"] == 1 and p["vaddr"] <= v < p["vaddr"] + p["filesz"]:
                return p["off"] + (v - p["vaddr"])
        raise ValueError("vaddr not in a PT_LOAD: " + hex(v))

    sections = {}
    if e_shoff:
        shstr = u64(e_shoff + e_shstrndx * e_shentsize + 24)
        for i in range(e_shnum):
            o = e_shoff + i * e_shentsize
            sh_name = u32(o)
            end = b.index(b"\x00", shstr + sh_name)
            name = b[shstr + sh_name:end].decode()
            sh_addr, sh_offset, sh_size = struct.unpack_from("<QQQ", b, o + 16)
            sections[name] = dict(addr=sh_addr, off=sh_offset, size=sh_size)

    dynamic = {}
    for p in phdrs:
        if p["type"] != 2:
            continue
        o, end = p["off"], p["off"] + p["filesz"]
        while o < end:
            tag, val = struct.unpack_from("<QQ", b, o)
            if tag == 0:
                break
            dynamic.setdefault(tag, val)
            o += 16
    return dict(phdrs=phdrs, sections=sections, dynamic=dynamic, v2o=v2o)


def find_plt_stub(elf, b: bytes, symbol: str) -> int:
    """Resolve the .plt stub of an imported symbol (dlopen/dlsym).

    AArch64 .plt layout: PLT0 (32 bytes) followed by one 16-byte stub per
    JMPREL entry, in relocation order."""
    dyn = elf["dynamic"]
    assert 23 in dyn and 2 in dyn, "no DT_JMPREL / DT_PLTRELSZ"
    jmprel, pltrelsz = elf["v2o"](dyn[23]), dyn[2]
    symtab, strtab = elf["v2o"](dyn[6]), elf["v2o"](dyn[5])

    def sym_name(idx):
        st_name = struct.unpack_from("<I", b, symtab + idx * 24)[0]
        end = b.index(b"\x00", strtab + st_name)
        return b[strtab + st_name:end].decode()

    plt = elf["sections"].get(".plt")
    assert plt, "no .plt section"
    for i in range(pltrelsz // 24):
        _r_offset, r_info, _addend = struct.unpack_from("<QQq", b, jmprel + i * 24)
        if sym_name(r_info >> 32) == symbol:
            return plt["addr"] + 32 + i * 16
    raise SystemExit(f"symbol {symbol!r} is not imported by this libil2cpp.so")


def find_cave(elf, b: bytes, size: int, reserved) -> int:
    """First zero run of `size` bytes, 4-byte aligned, inside an executable
    PT_LOAD (behind .text, where the segment padding lives) and clear of any
    reserved range."""
    needle = b"\x00" * size
    for p in elf["phdrs"]:
        if p["type"] != 1 or not (p["flags"] & 0x1):
            continue
        start, end = p["off"], p["off"] + p["filesz"]
        text = elf["sections"].get(".text")
        if text and start <= text["off"] and text["off"] + text["size"] <= end:
            start = text["off"] + text["size"]
        pos = start
        while True:
            idx = b.find(needle, pos, end)
            if idx < 0:
                break
            vaddr = p["vaddr"] + (idx - p["off"])
            if vaddr % 4 == 0 and not any(lo <= vaddr < hi or lo < vaddr + size <= hi
                                          for lo, hi in reserved):
                return vaddr
            pos = idx + 1
    raise SystemExit(f"no free zero cave of {size} bytes found")


# --------------------------------------------------------------------------
# cave / patch
# --------------------------------------------------------------------------

def displaced_words(b: bytes, rva: int, count: int):
    """Copy the first `count` instructions of the hooked method and prove they
    survive relocation (sp-relative and register-only forms only)."""
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    raw = b[rva:rva + count * 4]
    instructions = list(md.disasm(raw, rva))
    if len(instructions) != count:
        raise SystemExit("could not disassemble the displaced instructions")
    for ins in instructions:
        if ins.mnemonic in PC_RELATIVE:
            raise SystemExit(f"displaced instruction does not relocate: {ins.mnemonic} {ins.op_str}")
    return [struct.unpack_from("<I", raw, i * 4)[0] for i in range(count)], instructions


def build_cave(cave: int, words, resume: int, plt_dlopen: int, plt_dlsym: int) -> bytes:
    def at(offset):
        return cave + offset

    plan = [(lambda pc: sub_imm(31, 31, STACK_FRAME), "sub sp, sp, frame")]
    for i in range(8):                       # keep the caller's x0..x15
        plan.append((lambda pc, i=i: stp_off(2 * i, 2 * i + 1, 31, i * 0x10),
                     f"stp x{2 * i}, x{2 * i + 1}, [sp, #{i * 0x10:#x}]"))
    plan += [
        (lambda pc: adrp(0, pc, at(STR_LIB)), "adrp x0, lib"),
        (lambda pc: add_imm(0, 0, at(STR_LIB) & 0xFFF), "add x0, lib"),
        (lambda pc: 0x52800021, "mov w1, #1"),           # RTLD_LAZY
        (lambda pc: bl(pc, plt_dlopen), "bl dlopen"),
        (lambda pc: 0xDEAD0001, "cbz x0 -> restore"),     # patched below
        (lambda pc: str_imm(0, 31, 0x80), "str x0, [sp, #0x80] keep handle"),
        (lambda pc: adrp(1, pc, at(STR_SYM)), "adrp x1, sym"),
        (lambda pc: add_imm(1, 1, at(STR_SYM) & 0xFFF), "add x1, sym"),
        (lambda pc: ldr_imm(0, 31, 0x80), "ldr x0, [sp, #0x80]"),
        (lambda pc: bl(pc, plt_dlsym), "bl dlsym"),
        (lambda pc: 0xDEAD0002, "cbz x0 -> restore"),     # patched below
        (lambda pc: mov_reg(11, 0), "mov x11, x0 entry"),
        (lambda pc: ldr_imm(0, 31, 0x00), "ldr x0, [sp] this"),
        (lambda pc: ldr_imm(1, 31, 0x80), "ldr x1, [sp, #0x80] handle"),
        (lambda pc: blr(11), "blr x11"),
    ]
    restore_index = len(plan)
    for i in range(7, -1, -1):               # restore in reverse order
        plan.append((lambda pc, i=i: ldp_off(2 * i, 2 * i + 1, 31, i * 0x10),
                     f"restore ldp x{2 * i}, x{2 * i + 1}"))
    plan.append((lambda pc: add_imm(31, 31, STACK_FRAME), "add sp, sp, frame"))
    for word in words:                       # the displaced instruction(s)
        plan.append((lambda pc, w=word: w, "displaced instruction"))
    plan.append((lambda pc: b(pc, resume), "b entry+4 (resume the original)"))

    built = []
    for builder, _desc in plan:
        built.append(builder(at(len(built) * 4)))
    for index, (_builder, desc) in enumerate(plan):
        if desc.startswith("cbz"):
            built[index] = cbz(0, at(index * 4), at(restore_index * 4))

    blob = b"".join(struct.pack("<I", w & 0xFFFFFFFF) for w in built)
    code_len = len(blob)
    blob = blob.ljust(STR_LIB, b"\x00") + LIB_NAME.encode() + b"\x00"
    blob = blob.ljust(STR_SYM, b"\x00") + SYMBOL.encode() + b"\x00"
    return blob, code_len


def jumps_to(ins, target: int) -> bool:
    """capstone renders branch targets as `#0x1234`."""
    return ins.op_str.lstrip("#") == hex(target)


def verify(patched: bytes, rva: int, cave: int, code_len: int, resume: int,
           plt_dlopen: int, plt_dlsym: int) -> None:
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    print("--- entry hook ---")
    for ins in md.disasm(patched[rva:rva + 4], rva):
        print(f"0x{ins.address:x}: {ins.mnemonic}\t{ins.op_str}")
        assert ins.mnemonic == "b" and jumps_to(ins, cave), "entry hook does not branch to the cave"

    print("--- cave ---")
    cave_ins = list(md.disasm(patched[cave:cave + code_len], cave))
    for ins in cave_ins:
        print(f"0x{ins.address:x}: {ins.mnemonic}\t{ins.op_str}")
    assert any(ins.mnemonic == "bl" and jumps_to(ins, plt_dlopen) for ins in cave_ins), "no dlopen call"
    assert any(ins.mnemonic == "bl" and jumps_to(ins, plt_dlsym) for ins in cave_ins), "no dlsym call"
    assert any(ins.mnemonic == "ldr" and ins.op_str == "x0, [sp]" for ins in cave_ins), \
        "the saved `this` is not passed to the bridge"
    assert any(ins.mnemonic == "ldr" and ins.op_str == "x1, [sp, #0x80]" for ins in cave_ins), \
        "the dlopen handle is not passed to the bridge"
    assert not any(ins.mnemonic == "ret" for ins in cave_ins), "cave must not return"
    tail = cave_ins[-1]
    assert tail.mnemonic == "b" and jumps_to(tail, resume), \
        f"cave must resume the original method at {hex(resume)}"

    print("--- strings ---")
    lib = patched[cave + STR_LIB:cave + STR_LIB + 16].split(b"\x00")[0].decode()
    sym = patched[cave + STR_SYM:cave + STR_SYM + 32].split(b"\x00")[0].decode()
    print(f"lib={lib!r} sym={sym!r}")
    assert lib == LIB_NAME and sym == SYMBOL


def patch(data: bytes, rva: int, displace: int, cave, plt_dlopen, plt_dlsym):
    self_check_encoders()
    elf = parse_elf(data)
    if plt_dlopen is None:
        plt_dlopen = find_plt_stub(elf, data, "dlopen")
    if plt_dlsym is None:
        plt_dlsym = find_plt_stub(elf, data, "dlsym")
    if cave is None:
        cave = find_cave(elf, data, CAVE_SIZE, RESERVED)

    words, instructions = displaced_words(data, rva, displace)
    resume = rva + displace * 4
    print(f"entry rva=0x{rva:x} resume=0x{resume:x} cave=0x{cave:x} "
          f"plt dlopen=0x{plt_dlopen:x} dlsym=0x{plt_dlsym:x}")
    print("displaced: " + "; ".join(f"{i.mnemonic} {i.op_str}" for i in instructions))

    if any(data[cave:cave + CAVE_SIZE]):
        raise SystemExit("code cave is not zero-filled")
    blob, code_len = build_cave(cave, words, resume, plt_dlopen, plt_dlsym)
    if len(blob) > CAVE_SIZE:
        raise SystemExit("cave blob exceeds the reserved space")

    patched = bytearray(data)
    patched[rva:rva + 4] = struct.pack("<I", b(rva, cave))
    patched[cave:cave + len(blob)] = blob
    patched = bytes(patched)

    for start, end in ((0, rva), (rva + 4, cave), (cave + len(blob), len(data))):
        if patched[start:end] != data[start:end]:
            raise SystemExit(f"patch touched bytes outside its own ranges: [{start:#x}, {end:#x})")
    verify(patched, rva, cave, code_len, resume, plt_dlopen, plt_dlsym)
    return patched, cave


def main() -> None:
    argv = sys.argv[1:]
    if len(argv) < 2:
        raise SystemExit("usage: patch_title_voice.py <libil2cpp.so> <out.so> --rva 0x... "
                         "[--displace 1] [--cave 0x...] [--plt-dlopen 0x...] [--plt-dlsym 0x...]")
    src, dst = argv[0], argv[1]
    options = {"--rva": None, "--displace": 1, "--cave": None,
               "--plt-dlopen": None, "--plt-dlsym": None}
    i = 2
    while i < len(argv):
        key = argv[i]
        if key not in options or i + 1 >= len(argv):
            raise SystemExit(f"bad option {key}")
        options[key] = int(argv[i + 1], 0)
        i += 2
    if options["--rva"] is None:
        raise SystemExit("--rva is required: RVA of MainHallFSM.MainAniEnter in this libil2cpp.so")

    data = open(src, "rb").read()
    patched, cave = patch(data, options["--rva"], options["--displace"], options["--cave"],
                          options["--plt-dlopen"], options["--plt-dlsym"])
    open(dst, "wb").write(patched)
    print(f"patched {src} -> {dst} (cave 0x{cave:x})")


if __name__ == "__main__":
    main()
