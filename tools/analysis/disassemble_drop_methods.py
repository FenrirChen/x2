"""Read-only ARM64 disassembly of selected X2 IL2CPP methods.

Usage: python tools/analysis/disassemble_drop_methods.py 0x1e4845c [0x1e4bf34 ...]
"""
from __future__ import annotations

import bisect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".phase3_deps"))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM  # noqa: E402
from elftools.elf.elffile import ELFFile  # noqa: E402

methods = json.loads((ROOT / "tools/Il2CppDumper-bin/script.json").read_text(encoding="utf-8"))["ScriptMethod"]
by_addr = {int(row["Address"]): row["Name"] for row in methods}
starts = sorted(by_addr)
so = ROOT / "phase3_work/lib/arm64-v8a/libil2cpp.so"

with so.open("rb") as handle:
    elf = ELFFile(handle)
    for arg in sys.argv[1:]:
        start = int(arg, 0)
        index = bisect.bisect_right(starts, start)
        end = starts[index] if index < len(starts) else start + 0x1000
        segment = next(seg for seg in elf.iter_segments()
                       if seg["p_type"] == "PT_LOAD"
                       and seg["p_vaddr"] <= start < seg["p_vaddr"] + seg["p_filesz"])
        handle.seek(segment["p_offset"] + start - segment["p_vaddr"])
        blob = handle.read(end - start)
        print(f"\n### {by_addr.get(start, '?')} {start:#x}..{end:#x} ({end-start:#x})")
        for ins in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(blob, start):
            annotation = ""
            if ins.mnemonic in ("bl", "b") and ins.op_str.startswith("#0x"):
                target = int(ins.op_str[1:], 16)
                if target in by_addr:
                    annotation = f" ; {by_addr[target]}"
            print(f"{ins.address:#x} {ins.mnemonic:8} {ins.op_str}{annotation}")
