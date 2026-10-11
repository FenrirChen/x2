"""Locate dlopen/dlsym PLT stubs and candidate code caves in libil2cpp.so.

Read-only analysis used to compute the save-manager button trampoline patch.
"""
import struct
import sys

PATH = r"D:\demo\x2\apk\lib\arm64-v8a\libil2cpp.so"


def dyn_entries(b, phdrs):
    for p in phdrs:
        if p['type'] == 2:
            o, end = p['off'], p['off'] + p['filesz']
            entries = []
            while o < end:
                tag, val = struct.unpack_from('<QQ', b, o)
                if tag == 0:
                    break
                entries.append((tag, val))
                o += 16
            return entries
    return []


def main():
    b = open(PATH, 'rb').read()
    e_phoff = struct.unpack_from('<Q', b, 0x20)[0]
    e_phentsize = struct.unpack_from('<H', b, 0x36)[0]
    e_phnum = struct.unpack_from('<H', b, 0x38)[0]
    e_shoff = struct.unpack_from('<Q', b, 0x28)[0]
    e_shentsize = struct.unpack_from('<H', b, 0x3A)[0]
    e_shnum = struct.unpack_from('<H', b, 0x3C)[0]
    e_shstrndx = struct.unpack_from('<H', b, 0x3E)[0]
    phdrs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type = struct.unpack_from('<I', b, o)[0]
        p_offset, p_vaddr, _pa, p_filesz = struct.unpack_from('<QQQQ', b, o + 8)
        phdrs.append(dict(type=p_type, off=p_offset, vaddr=p_vaddr, filesz=p_filesz))

    def v2o(v):
        for p in phdrs:
            if p['type'] == 1 and p['vaddr'] <= v < p['vaddr'] + p['filesz']:
                return p['off'] + (v - p['vaddr'])
        raise ValueError(hex(v))

    d = dyn_entries(b, phdrs)
    tags = dict(d)
    symtab = v2o(tags[6])
    strtab = v2o(tags[5])
    jmprel = tags.get(23)          # DT_JMPREL
    pltrelsz = tags.get(2, 0)      # DT_PLTRELSZ
    pltgot = tags.get(3)           # DT_PLTGOT
    print(f"jmprel=0x{jmprel:x} pltrelsz=0x{pltrelsz:x} pltgot=0x{pltgot:x}")

    def sym_name(idx):
        so = symtab + idx * 24
        st_name = struct.unpack_from('<I', b, so)[0]
        end = b.index(b'\x00', strtab + st_name)
        return b[strtab + st_name:end].decode()

    wanted = {}
    for i in range(pltrelsz // 24):
        off = v2o(jmprel) + i * 24
        r_offset, r_info, _addend = struct.unpack_from('<QQq', b, off)
        sym_idx = r_info >> 32
        name = sym_name(sym_idx)
        if name in ('dlopen', 'dlsym'):
            wanted[name] = i
    print("reloc indexes:", wanted)

    # section headers to find .plt address
    shstr_off = struct.unpack_from('<Q', b, e_shoff + e_shstrndx * e_shentsize + 24)[0]
    sections = {}
    for i in range(e_shnum):
        o = e_shoff + i * e_shentsize
        sh_name = struct.unpack_from('<I', b, o)[0]
        end = b.index(b'\x00', shstr_off + sh_name)
        name = b[shstr_off + sh_name:end].decode()
        sh_type, _flags = struct.unpack_from('<II', b, o + 4)
        sh_addr, sh_offset, sh_size = struct.unpack_from('<QQQ', b, o + 16)
        sections[name] = dict(addr=sh_addr, off=sh_offset, size=sh_size, type=sh_type)
    for name in ('.plt', '.text', '.got.plt', '.data', '.bss'):
        s = sections.get(name)
        if s:
            print(f"{name}: addr=0x{s['addr']:x} size=0x{s['size']:x}")
    plt = sections['.plt']
    for name, idx in wanted.items():
        stub = plt['addr'] + 32 + idx * 16
        print(f"PLT {name}: 0x{stub:x} (stub bytes {b[plt['off'] + 32 + idx * 16:plt['off'] + 32 + idx * 16 + 4].hex()})")

    # code caves: zero runs >= 256 bytes inside the first LOAD (code segment),
    # after .plt and before end of segment
    seg = phdrs[0]
    start = seg['off'] + 0x1000
    end = seg['off'] + seg['filesz']
    run_start = None
    caves = []
    step = 4
    pos = start
    zeros = 0
    run = None
    while pos < end:
        chunk = b[pos:pos + 4]
        if chunk == b'\x00\x00\x00\x00':
            if run is None:
                run = pos
        else:
            if run is not None and pos - run >= 256:
                caves.append((run, pos - run))
            run = None
        pos += 4
        if len(caves) >= 8:
            break
    for c_off, size in caves:
        # convert file offset to vaddr
        v = c_off - seg['off'] + seg['vaddr']
        print(f"cave: file=0x{c_off:x} vaddr=0x{v:x} size={size}")


if __name__ == '__main__':
    main()
