"""Disassemble the visitor-login button handler region in libil2cpp.so."""
import sys
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

path = r"D:\demo\x2\apk\lib\arm64-v8a\libil2cpp.so"
data = open(path, 'rb').read()
md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
md.detail = False

start = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x15166F0
count = int(sys.argv[2]) if len(sys.argv) > 2 else 40
code = data[start:start + count * 4]
for ins in md.disasm(code, start):
    print(f"0x{ins.address:x}: {ins.mnemonic}\t{ins.op_str}")
