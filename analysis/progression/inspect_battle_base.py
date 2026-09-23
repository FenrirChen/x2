"""Resolve named base-property wrappers in the bounded AddBaseProperty method."""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT / '.phase3_deps'))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from elftools.elf.elffile import ELFFile

data = json.loads((ROOT / 'tools/Il2CppDumper-bin/script.json').read_text(encoding='utf-8'))
strings = {r['Address']:r['Value'] for r in data['ScriptString']}
with (ROOT / 'phase3_work/lib/arm64-v8a/libil2cpp.so').open('rb') as stream:
    elf = ELFFile(stream)
    segments = list(elf.iter_segments())
    def read(address,size):
        for segment in segments:
            if segment['p_type'] == 'PT_LOAD' and segment['p_vaddr'] <= address < segment['p_vaddr']+segment['p_filesz']:
                stream.seek(segment['p_offset']+address-segment['p_vaddr'])
                return stream.read(size)
        return bytes(size)
    registers = {}
    field = None
    for ins in Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(read(0x1C21434,0x5ac),0x1C21434):
        import re
        if ins.mnemonic in ('ldr','ldrsw') and ins.op_str.startswith('x1, [x20,'):
            field = ins.op_str
        if ins.mnemonic == 'adrp':
            reg,addr = ins.op_str.split(', #')
            registers[reg] = int(addr,0)
        if ins.mnemonic == 'ldr':
            match = re.fullmatch(r'(x\d+), \[(x\d+), #(0x[0-9a-f]+)\]',ins.op_str)
            if match and match[2] in registers:
                pointer = struct.unpack('<Q',read(registers[match[2]]+int(match[3],0),8))[0]
                if pointer in strings:
                    print(hex(ins.address),field,strings[pointer])
