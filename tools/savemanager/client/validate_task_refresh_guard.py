"""Emulate the season task event guard and displaced ARM64 prologue."""
import json
import struct
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'runtime/client_release20261024/deps'))
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM
from unicorn import arm64_const as C


def validate(native, audit):
    data = Path(native).read_bytes()
    report = json.loads(Path(audit).read_text(encoding='utf8'))
    uc = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    uc.mem_map(0, (len(data) + 4095) // 4096 * 4096)
    uc.mem_write(0, data)
    uc.reg_write(C.UC_ARM64_REG_CPACR_EL1, 3 << 20)
    stack = 0x70000000
    stop = 0x6000000
    uc.mem_map(stack, 0x20000)
    uc.mem_map(stop, 4096)
    checked = 0
    for kind in [-1, *range(26), 15, 32767]:
        initial = {getattr(C, f'UC_ARM64_REG_X{i}'): 0x120000 + i * 32 for i in range(31)}
        initial.update({getattr(C, f'UC_ARM64_REG_Q{i}'): ((i + 17) << 96) + i for i in range(32)})
        initial[C.UC_ARM64_REG_X1] = kind & 0xffffffff
        initial[C.UC_ARM64_REG_X30] = stop
        for reg, value in initial.items():
            uc.reg_write(reg, value)
        sp = stack + 0x10000
        uc.reg_write(C.UC_ARM64_REG_SP, sp)
        uc.mem_write(sp - 96, bytes(96))
        uc.emu_start(report['hook'], report['resume'] if kind == 15 else stop, count=10)
        assert all(uc.reg_read(reg) == value for reg, value in initial.items()), kind
        assert uc.reg_read(C.UC_ARM64_REG_SP) == sp - (96 if kind == 15 else 0), kind
        if kind == 15:
            expected = struct.pack('<QQ', initial[C.UC_ARM64_REG_Q9] & ((1 << 64) - 1),
                                   initial[C.UC_ARM64_REG_Q8] & ((1 << 64) - 1))
            assert bytes(uc.mem_read(sp - 96, 16)) == expected
        else:
            assert bytes(uc.mem_read(sp - 96, 96)) == bytes(96)
        checked += 1
    result = {'cases': checked, 'ordinary_task_events': 'return without touching UI or stack',
              'season_task_events': 'original prologue and body retained on every refresh', 'result': 'passed'}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    validate(*sys.argv[1:3])
