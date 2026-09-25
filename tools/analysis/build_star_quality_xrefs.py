"""Read-only full-binary call-graph scan for equipment star/quality research.

Disassembles every IL2CPP method range in libil2cpp.so once, records BL targets,
and emits reverse xref tables for the star/quality investigation.

Usage: python tools/analysis/build_star_quality_xrefs.py
Outputs: analysis/equipment/callgraph_bl.json  (caller -> targets, target -> callers)
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

OUT = ROOT / "x2_revive_workspace/analysis/equipment/callgraph_bl.json"

methods = json.loads(
    (ROOT / "tools/Il2CppDumper-bin/script.json").read_text(encoding="utf-8")
)["ScriptMethod"]
starts = sorted(int(row["Address"]) for row in methods)

so = ROOT / "phase3_work/lib/arm64-v8a/libil2cpp.so"

callers_of: dict[str, set[str]] = {}
callees_of: dict[str, set[str]] = {}

cs = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
cs.detail = False

with so.open("rb") as handle:
    elf = ELFFile(handle)
    segments = [seg for seg in elf.iter_segments() if seg["p_type"] == "PT_LOAD"]

    for row in methods:
        start = int(row["Address"])
        idx = bisect.bisect_right(starts, start)
        end = starts[idx] if idx < len(starts) else start + 0x800
        seg = next(
            (s for s in segments
             if s["p_vaddr"] <= start < s["p_vaddr"] + s["p_filesz"]),
            None,
        )
        if seg is None:
            continue
        handle.seek(seg["p_offset"] + start - seg["p_vaddr"])
        blob = handle.read(min(end - start, 0x20000))
        caller = row["Name"]
        tgts = callees_of.setdefault(caller, set())
        try:
            for ins in cs.disasm(blob, start):
                if ins.mnemonic in ("bl",) and ins.op_str.startswith("#0x"):
                    tgt = int(ins.op_str[1:], 16)
                    tgts.add(hex(tgt))
        except Exception:
            pass

# build reverse map with names
addr2name = {int(row["Address"]): row["Name"] for row in methods}
for caller in list(callees_of.keys()):
    for t in list(callees_of[caller]):
        taddr = int(t, 16)
        tname = addr2name.get(taddr, t)
        callees_of[caller].add(tname)
        callers_of.setdefault(tname, set()).add(caller)

result = {
    "generated": "2026-09-25",
    "method_count": len(methods),
    "callees_of": {k: sorted(v) for k, v in sorted(callees_of.items())},
    "callers_of": {k: sorted(v) for k, v in sorted(callers_of.items())},
}
OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"wrote {OUT} methods={len(methods)} edges={sum(len(v) for v in callees_of.values())}")
