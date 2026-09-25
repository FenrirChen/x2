"""PART D: false-complete / hardcode / stub / compat audit over the Revival server.

Deterministic regex audit; read-only. Outputs:
  analysis/coverage/hardcoded_business_rules.json
  docs/knowledge/coverage/false_complete_audit.md
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_JSON = REPO / "analysis" / "coverage" / "hardcoded_business_rules.json"
OUT_MD = REPO / "docs" / "false_complete_audit.md"
OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

SCAN_DIRS = [REPO / "src/x2server", REPO / "tools"]
TEST_MARK = ("test",)

MARKERS = [
    ("TODO", r"\bTODO\b"), ("FIXME", r"\bFIXME\b"), ("HACK", r"\bHACK\b"),
    ("XXX", r"\bXXX\b"), ("STUB", r"\bSTUB\b"),
    ("placeholder", r"placeholder", ), ("compat", r"\bcompat",),
    ("temporary", r"temporar|\btemp\b|临时"), ("fallback", r"fallback"),
    ("mock", r"\bmock",), ("fake", r"\bfake\b"),
]

SAMPLE_IDS = {
    "1003": "hero Behemoth (dev sample)",
    "2110801": "first main section (dev sample)",
    "2110802": "second main section (dev sample)",
    "2110803": "third main section (dev sample)",
    "2130101": "gold resource dungeon (dev sample)",
    "2030100": "daily dungeon id (dev sample)",
    "2010000": "main chapter (dev sample)",
    "2110001": "main chapter/section seed (dev sample)",
    "1237901": "gold item id",
    "1237907": "god exp item id",
    "1201003": "behemoth chip item id",
    "1201000": "universal chip item id",
}

STUB_RETURN = re.compile(r"return\s+(?:\[\]|\{\}|None|10|13|208|False)\b")

hits = []
for base in SCAN_DIRS:
    for f in sorted(base.rglob("*.py")):
        rel = f.relative_to(REPO).as_posix()
        if "__pycache__" in rel or rel.startswith("tools/analysis/"):
            continue
        is_test = rel.startswith("tests/") or "test_" in f.name or f.name.startswith("test")
        src = f.read_text(encoding="utf-8", errors="replace")
        for ln, line in enumerate(src.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") and "TODO" not in stripped:
                pass
            entry_note = None
            for label, pat in MARKERS:
                if re.search(pat, line, re.I):
                    cls = "BENIGN_TEST_CONSTANT" if is_test else "TEMP_COMPAT"
                    hits.append({"file": rel, "line": ln, "kind": "MARKER:" + label,
                                 "text": stripped[:160], "classification": cls})
                    break
            # hardcoded ids in src (not tests)
            if not is_test:
                for sid, note in SAMPLE_IDS.items():
                    if re.search(rf"(?<![\w.]){sid}(?![\w.])", line):
                        cls = ("DATA_DRIVEN_DEFAULT"
                               if re.search(r"[=#()\[\s,{]1237901|item|gift|gold", line, re.I)
                               else "SINGLE_SAMPLE_IMPLEMENTATION")
                        hits.append({"file": rel, "line": ln, "kind": "HARDCODED_ID:" + sid,
                                     "text": stripped[:160], "classification": cls,
                                     "note": note})
                        break
            # stub-looking returns in handler files
            if not is_test and re.search(r"def |return ", stripped):
                m = STUB_RETURN.search(stripped)
                if m and re.search(r"code|result|success|error", stripped, re.I):
                    hits.append({"file": rel, "line": ln, "kind": "FIXED_RETURN",
                                 "text": stripped[:160],
                                 "classification": "FALSE_COMPLETE_RISK"})

# de-dup identical (file,line)
seen = set()
dedup = []
for h in hits:
    k = (h["file"], h["line"], h["kind"])
    if k in seen:
        continue
    seen.add(k)
    dedup.append(h)
hits = dedup

by_class = Counter(h["classification"] for h in hits)
by_file = Counter(h["file"] for h in hits)
print("hits:", len(hits), dict(by_class))
print("top files:", by_file.most_common(10))

json.dump({"generated_by": "tools/analysis/audit_hardcodes.py",
           "scan_roots": ["src/x2server", "tools"],
           "hit_count": len(hits),
           "classification_counts": dict(by_class),
           "hits": hits}, OUT_JSON.open("w", encoding="utf-8"), ensure_ascii=False, indent=1)

# markdown: group by classification, exclude tests from prominent listing
lines = ["# 假完成 / 硬编码 / Compat / Stub 审计", "",
         f"扫描范围：`src/x2server/` 与 `tools/`（测试文件命中标 BENIGN_TEST_CONSTANT，不展开）。"
         f"共 {len(hits)} 处命中；机器可读：`analysis/coverage/hardcoded_business_rules.json`。", ""]
for cls in ("FALSE_COMPLETE_RISK", "SINGLE_SAMPLE_IMPLEMENTATION", "TEMP_COMPAT",
            "DATA_DRIVEN_DEFAULT", "BENIGN_TEST_CONSTANT"):
    items = [h for h in hits if h["classification"] == cls]
    if not items:
        continue
    lines += [f"## {cls}（{len(items)}）", ""]
    if cls == "BENIGN_TEST_CONSTANT":
        files = Counter(h["file"] for h in items)
        lines += [f"仅列出文件分布：{dict(files)}", ""]
        continue
    for h in items[:60]:
        lines.append(f"- `{h['file']}:{h['line']}` [{h['kind']}] `{h['text']}`"
                     + (f" — {h['note']}" if h.get("note") else ""))
    if len(items) > 60:
        lines.append(f"- …其余 {len(items)-60} 条见 JSON")
    lines.append("")
OUT_MD.write_text("\n".join(lines), encoding="utf-8")
print("wrote", OUT_MD)
