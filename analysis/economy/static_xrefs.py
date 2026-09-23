"""Read selected IL2CPP ARM64 methods; never runs client code."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.phase3_deps'))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile

DUMP = (ROOT / 'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf-8')
METHODS = json.loads((ROOT / 'tools/Il2CppDumper-bin/script.json').read_text(encoding='utf-8'))['ScriptMethod']
BY_ADDR = {int(m['Address']): m['Name'] for m in METHODS}
ALL_ADDR = sorted(BY_ADDR)
SO = ROOT / 'phase3_work/lib/arm64-v8a/libil2cpp.so'

def method_addr(klass: str, method: str):
    pattern = re.compile(r'// Namespace: [^\n]*\n(?:public|internal|private) class ' + re.escape(klass) + r'[^\n]*\n\{(.*?)(?=\n\}\n\n// Namespace:)', re.S)
    match = pattern.search(DUMP)
    if not match: raise ValueError(klass)
    needle = re.compile(r'// RVA: (0x[\dA-F]+)[^\n]*\n\s*(?:public|private|protected|internal)[^\n]*\b' + re.escape(method) + r'\(')
    found = needle.search(match.group(1))
    if not found: raise ValueError(klass + '.' + method)
    return int(found.group(1), 16)

def calls(klass: str, method: str):
    start = method_addr(klass, method)
    higher = [a for a in ALL_ADDR if a > start]
    size = min((higher[0] - start) if higher else 0x1000, 0x4000)
    with SO.open('rb') as fh:
        elf = ELFFile(fh)
        seg = next(s for s in elf.iter_segments() if s['p_type']=='PT_LOAD' and s['p_vaddr'] <= start < s['p_vaddr']+s['p_filesz'])
        fh.seek(seg['p_offset'] + start - seg['p_vaddr'])
        blob = fh.read(size)
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    out=[]
    for ins in md.disasm(blob, start):
        if ins.mnemonic in ('bl','b') and ins.op_str.startswith('#0x'):
            target=int(ins.op_str[1:],16)
            if target in BY_ADDR:
                out.append((hex(ins.address),BY_ADDR[target]))
    return start, size, out

if __name__ == '__main__':
    for spec in sys.argv[1:]:
        klass, method = spec.split('.',1)
        addr, size, result = calls(klass,method)
        print(f'### {spec} RVA={addr:#x} size={size:#x}')
        for at, name in result: print(at,name)
