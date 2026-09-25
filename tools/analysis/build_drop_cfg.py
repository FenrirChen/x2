"""Build the complete basic-block listing for GetDropItemByGroup from ARM64 bytes."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".phase3_deps"))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM  # noqa: E402
from elftools.elf.elffile import ELFFile  # noqa: E402

START, END = 0x1E4845C, 0x1E48B0C
SO = ROOT / "phase3_work/lib/arm64-v8a/libil2cpp.so"
METHODS = json.loads((ROOT / "tools/Il2CppDumper-bin/script.json").read_text(encoding="utf-8"))["ScriptMethod"]
BY_ADDR = {int(method["Address"]): method["Name"] for method in METHODS}
with SO.open("rb") as handle:
    elf = ELFFile(handle)
    segment = next(seg for seg in elf.iter_segments()
                   if seg["p_type"] == "PT_LOAD"
                   and seg["p_vaddr"] <= START < seg["p_vaddr"] + seg["p_filesz"])
    handle.seek(segment["p_offset"] + START - segment["p_vaddr"])
    code = handle.read(END - START)
instructions = list(Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(code, START))
assert len(instructions) * 4 == END - START


def is_branch(ins):
    return ins.mnemonic == "b" or ins.mnemonic.startswith("b.") or ins.mnemonic in {
        "cbz", "cbnz", "tbz", "tbnz", "ret", "br"}


def target(ins):
    # tbz/tbnz also contain a bit-number immediate; the branch target is last.
    hits = re.findall(r"#(0x[0-9a-f]+)", ins.op_str)
    return int(hits[-1], 16) if hits else None


leaders = {START}
for ins in instructions:
    if is_branch(ins):
        dest = target(ins)
        if dest is not None and START <= dest < END:
            leaders.add(dest)
        if ins.address + 4 < END:
            leaders.add(ins.address + 4)
leaders = sorted(leaders)
blocks = []
for index, begin in enumerate(leaders):
    stop = leaders[index + 1] if index + 1 < len(leaders) else END
    body = [ins for ins in instructions if begin <= ins.address < stop]
    if not body:
        continue
    last = body[-1]
    edges = []
    dest = target(last)
    if is_branch(last) and dest is not None:
        edges.append(f"{dest:#x}")
    if last.mnemonic != "ret" and last.mnemonic != "br" and last.mnemonic != "b" and stop < END:
        edges.append(f"{stop:#x}")
    blocks.append((begin, stop, body, edges))

lines = ["# GetDropItemByGroup 完整 ARM64 CFG", "",
         "目标实际属于 `LogicX2.DropItemManager`，不是 `DropPropManager`。",
         f"`dump.cs` RVA/VA `{START:#x}`；函数字节范围 `{START:#x}..{END:#x}`；"
         f"{len(instructions)} 条指令、{len(blocks)} 个 basic blocks。", "",
         "分块按所有条件/无条件跳转目标与后继指令机械生成；BL 视作调用，不切块。"
         "下表每块的最后一条指令给出边。异常/空指针辅助调用视为外部调用。", "",
         "| Block | Instructions | Last instruction | Outgoing edges |", "|---|---:|---|---|",]
for begin, stop, body, edges in blocks:
    last = body[-1]
    lines.append(f"| `{begin:#x}..{stop:#x}` | {len(body)} | "
                 f"`{last.mnemonic} {last.op_str}` | {', '.join(f'`{edge}`' for edge in edges) or 'return'} |")
lines += ["", "## 全指令（含调用目标）", "", "```text"]
for ins in instructions:
    annotation = ""
    if ins.mnemonic in ("bl", "b"):
        dest = target(ins)
        if dest in BY_ADDR:
            annotation = f" ; {BY_ADDR[dest]}"
    lines.append(f"{ins.address:#x}  {ins.mnemonic:8} {ins.op_str}{annotation}")
lines += ["```", ""]
out = ROOT / "x2_revive_workspace/analysis/drop_algorithm/get_drop_item_by_group_cfg.md"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(lines), encoding="utf-8")
print(f"wrote {out} ({len(blocks)} blocks, {len(instructions)} instructions)")
