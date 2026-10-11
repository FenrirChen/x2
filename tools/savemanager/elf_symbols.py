"""Inspect ELF dynamic symbols/imports for libil2cpp.so (read-only analysis)."""
import struct
import sys


def u16(b, o):
    return struct.unpack_from('<H', b, o)[0]


def u32(b, o):
    return struct.unpack_from('<I', b, o)[0]


def u64(b, o):
    return struct.unpack_from('<Q', b, o)[0]


def parse(path):
    b = open(path, 'rb').read()
    assert b[:4] == b'\x7fELF', 'not ELF'
    is64 = b[4] == 2
    assert is64
    e_phoff = u64(b, 0x20)
    e_phentsize = u16(b, 0x36)
    e_phnum = u16(b, 0x38)
    phdrs = []
    for i in range(e_phnum):
        o = e_phoff + i * e_phentsize
        p_type, p_flags = u32(b, o), u32(b, o + 4)
        p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_align = struct.unpack_from('<QQQQQQ', b, o + 8)
        phdrs.append(dict(type=p_type, off=p_offset, vaddr=p_vaddr, filesz=p_filesz))
    dyn = next((p for p in phdrs if p['type'] == 2), None)  # PT_DYNAMIC
    entries = []
    o = dyn['off']
    while True:
        tag, val = struct.unpack_from('<QQ', b, o)
        if tag == 0:
            break
        entries.append((tag, val))
        o += 16
    def vaddr_to_off(v):
        for p in phdrs:
            if p['type'] == 1 and p['vaddr'] <= v < p['vaddr'] + p['filesz']:
                return p['off'] + (v - p['vaddr'])
        raise ValueError(hex(v))
    strtab = symtab = None
    strsz = 0
    hash_vaddr = None
    for tag, val in entries:
        if tag == 5:
            strtab = vaddr_to_off(val)
        elif tag == 10:
            strsz = val
        elif tag == 6:
            symtab = val
        elif tag == 4:
            hash_vaddr = val
    symcount = None
    if hash_vaddr is not None:
        ho = vaddr_to_off(hash_vaddr)
        symcount = u32(b, ho + 4)  # nchain == symbol count
    out = {'imports': [], 'exports': []}
    if symcount and symtab:
        symtab_off = vaddr_to_off(symtab)
        for i in range(symcount):
            so = symtab_off + i * 24
            st_name, st_info, st_other, st_shndx, st_value, st_size = struct.unpack_from('<IBBHQQ', b, so)
            if st_name == 0 or st_name >= strsz:
                continue
            name = b[strtab + st_name:b.index(b'\x00', strtab + st_name)].decode('utf-8', 'replace')
            bind = st_info >> 4
            if st_shndx == 0:
                if name:
                    out['imports'].append(name)
            elif bind in (1, 2, 10) and st_value:  # GLOBAL/WEAK
                out['exports'].append((name, st_value, st_size))
    return out


if __name__ == '__main__':
    path = sys.argv[1]
    info = parse(path)
    imp = info['imports']
    print('IMPORTS:', len(imp))
    interesting = [n for n in imp if n in ('dlopen', 'dlsym', 'dladdr', 'dlclose', '__loader_dlopen')]
    print('  linker imports:', interesting)
    exp = info['exports']
    print('EXPORTS:', len(exp))
    api = [n for n, v, s in exp if n.startswith('il2cpp_')]
    print('  il2cpp_* exports:', len(api))
    keys = ['il2cpp_domain_get', 'il2cpp_thread_attach', 'il2cpp_class_from_name',
            'il2cpp_class_get_field_from_name', 'il2cpp_field_get_value',
            'il2cpp_runtime_invoke', 'il2cpp_string_new', 'il2cpp_string_chars',
            'il2cpp_object_new', 'il2cpp_get_corlib', 'il2cpp_domain_get_assemblies',
            'il2cpp_image_get_name', 'il2cpp_class_get_method_from_name',
            'il2cpp_field_get_offset', 'il2cpp_method_get_name']
    for k in keys:
        hit = [v for n, v, s in exp if n == k]
        if hit:
            print('  %s: YES @0x%x size=%d' % (k, hit[0], [s for n, v, s in exp if n == k][0]))
        else:
            print('  %s: no' % k)
    # look for dlopen-related exports and other useful
    print('  sample exports:', sorted(n for n, v, s in exp)[:12])
