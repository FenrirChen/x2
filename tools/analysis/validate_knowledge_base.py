"""Knowledge base validator (light lint, per governance rules).

Checks:
  1. Markdown dead links (relative targets must exist)
  2. PROJECT_INDEX referenced paths exist
  3. Current Knowledge docs have the metadata header
  4. Evidence manifest paths exist
  5. No duplicate canonical among knowledge docs (same basename in knowledge twice)
  6. History files follow YYYY-MM-DD_NN_ naming and have a metadata header
  7. docs root contains no stray .md (governance)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
problems = []

# 1+2: links
md_files = [p for p in REPO.rglob("*.md")
            if "__pycache__" not in str(p) and not str(p).replace("\\", "/").startswith(".git/")]
link_re = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
dead = 0
checked = 0
for md in md_files:
    text = md.read_text(encoding="utf-8", errors="replace")
    for m in link_re.finditer(text):
        target = m.group(1).strip()
        if target.startswith(("http://", "https://", "mailto:", "D:/", "D:\\", "d:/")):
            continue
        checked += 1
        base = md.parent
        resolved = (base / target).resolve()
        if not resolved.exists():
            problems.append(f"DEAD LINK: {md.relative_to(REPO)} -> {target}")
            dead += 1

# 3: knowledge metadata
for md in (REPO / "docs/knowledge").rglob("*.md"):
    head = md.read_text(encoding="utf-8", errors="replace")[:400]
    if "Document-Type: Current Knowledge" not in head:
        problems.append(f"KNOWLEDGE MISSING METADATA: {md.relative_to(REPO)}")

# 4: evidence manifest paths
manifest = json.loads((REPO / "evidence/manifests/evidence_manifest.json").read_text(encoding="utf-8"))
for e in manifest["entries"]:
    if not e.get("exists"):
        problems.append(f"MANIFEST MISSING: {e['id']} -> {e['path']}")

# 5: duplicate canonical basenames in knowledge tree (domain README.md allowed)
seen = {}
for md in (REPO / "docs/knowledge").rglob("*.md"):
    seen.setdefault(md.name, []).append(str(md.relative_to(REPO)))
for name, paths in seen.items():
    if len(paths) > 1 and name != "README.md":
        problems.append(f"DUPLICATE CANONICAL NAME: {name} -> {paths}")

# 6: history naming/metadata
hist_re = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}_.+\.md$")
HISTORY_OVERLAYS = {"README.md", "PROJECT_TIMELINE.md", "SUPERSEDED_KNOWLEDGE.md"}
for md in (REPO / "docs/history").glob("*.md"):
    if md.name in HISTORY_OVERLAYS:
        continue
    if not hist_re.match(md.name):
        problems.append(f"HISTORY BAD NAME: {md.name}")
    else:
        head = md.read_text(encoding="utf-8", errors="replace")[:400]
        if "Document-Type: Historical Report" not in head and "SUPERSEDED" not in head:
            problems.append(f"HISTORY MISSING METADATA: {md.name}")

# 7: docs root stray files (PATH_MIGRATION.md / README.md are intentional)
ALLOWED_DOCS_ROOT = {"README.md", "PATH_MIGRATION.md", "knowledge_reorg_final_tree.md", "knowledge_reorg_inventory.md", "equipment_instance_server_fix_plan.md"}
stray = [p.name for p in (REPO / "docs").iterdir() if p.is_file() and p.name not in ALLOWED_DOCS_ROOT]
if stray:
    problems.append(f"DOCS ROOT STRAY FILES: {stray}")

print(f"md files: {len(md_files)}; links checked: {checked}; problems: {len(problems)}")
for p in problems:
    print("  -", p)
sys.exit(1 if problems else 0)
