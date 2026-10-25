"""Halve ActivityBox.CostNum in all three table readers, preserving other data.
Purchase shops already take listing/popup prices from server messages.
"""
import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent / '.phase3_deps'),
               str(ROOT / 'runtime/client_release20261024/deps')]
from tools.savemanager.client.patch_activity_ui import branch
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn import arm64_const as C

HOOKS = (0x1C3D5D0, 0x1C3DB10, 0x1C3E08C)
CAVE = 0x4293600


def patch(apk, output):
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apk) as archive:
        old = archive.read('lib/arm64-v8a/libil2cpp.so')
    data = bytearray(old)
    global CAVE
    from tools.savemanager.client import patch_title_voice as native
    from tools.savemanager.client.patch_task_refresh_guard import branch_target
    reserved = tuple(native.RESERVED) + tuple((branch_target(old,h), branch_target(old,h)+size) for h,size in ((0x13BDA24,1024),(0x1E497D8,64),(0x14C928C,64)))
    CAVE = native.find_cave(native.parse_elf(old), old, 128, reserved)
    checks = 0
    changed = set()
    for index, hook in enumerate(HOOKS):
        cave = CAVE + index * 32
        assert old[hook:hook+4] == struct.pack('<I', 0xB9002A75), hex(hook)
        assert not any(old[cave:cave+32]), hex(cave)
        # Preserve x8/x9 and flags. Leave decoded w21 unchanged for reader logic.
        words = [0xA9BF27E8, 0x53017EA8, 0xB9002A68, 0xA8C127E8,
                 branch(cave+16, hook+4)]
        code = struct.pack('<5I', *words)
        data[cave:cave+20] = code
        struct.pack_into('<I', data, hook, branch(hook, cave))
        changed.update(range(hook,hook+4)); changed.update(range(cave,cave+20))
        uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        uc.mem_map(hook & ~4095, 4096)
        uc.mem_map(cave & ~4095, 4096)
        uc.mem_write(hook, bytes(data[hook:hook+4])); uc.mem_write(cave,code)
        uc.mem_map(0x70000000, 0x20000)
        for price in [0,1,2,3,25,50,67,127,128,150,200,255,500,999,2**31-1]:
            initial = {getattr(C,f'UC_ARM64_REG_X{i}'):0x123400+i*16 for i in range(31)}
            initial[C.UC_ARM64_REG_X19]=0x70001000
            initial[C.UC_ARM64_REG_X21]=price
            for reg,value in initial.items():uc.reg_write(reg,value)
            uc.reg_write(C.UC_ARM64_REG_SP,0x70010000)
            uc.reg_write(C.UC_ARM64_REG_NZCV,0xA0000000)
            uc.emu_start(hook,hook+4,count=12)
            assert struct.unpack('<I',uc.mem_read(0x70001028,4))[0] == price//2
            assert all(uc.reg_read(reg)==value for reg,value in initial.items())
            assert uc.reg_read(C.UC_ARM64_REG_SP)==0x70010000
            assert uc.reg_read(C.UC_ARM64_REG_NZCV)==0xA0000000
            checks+=1
    assert len(data)==len(old)
    assert all(a==b or i in changed for i,(a,b) in enumerate(zip(old,data)))
    (output/'libil2cpp.so').write_bytes(data)
    (output/'manifest.json').write_text('{}',encoding='utf8')
    report={'hooks':list(HOOKS),'cave':CAVE,'emulated_cases':checks,
            'rounding':'floor unit price before multiplying draw count',
            'source_sha256':hashlib.sha256(old).hexdigest(),
            'native_sha256':hashlib.sha256(data).hexdigest(),
            'disassembly':[f'{i.address:x} {i.mnemonic} {i.op_str}' for i in
                Cs(CS_ARCH_ARM64,CS_MODE_ARM).disasm(code,cave)]}
    (output/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('apk',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();patch(a.apk,a.output)
