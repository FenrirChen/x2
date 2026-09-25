"""PART E: SQLite schema catalog + state lifecycle / relog / refresh audit.

Deterministic static analysis of src/x2server (no active DB is opened).
Outputs:
  analysis/persistence/sqlite_schema_catalog.json
  analysis/persistence/state_lifecycle.json
  docs/knowledge/persistence/persistence_relog_audit.md
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "persistence"
OUT.mkdir(parents=True, exist_ok=True)
SRC = REPO / "src" / "x2server"

MODULES = {}
for f in sorted(SRC.rglob("*.py")):
    MODULES[f.relative_to(REPO).as_posix()] = f.read_text(encoding="utf-8", errors="replace")

# ---------- 1. schema catalog ----------
tables = {}
for rel, src in MODULES.items():
    for m in re.finditer(r'CREATE TABLE IF NOT EXISTS (\w+)\s*\((.*?)\)"""\)', src, re.S):
        name, body = m.group(1), m.group(2)
        cols = []
        for line in body.splitlines():
            line = line.strip().rstrip(",")
            if not line or line.upper().startswith(("PRIMARY KEY", "UNIQUE", "CHECK", "FOREIGN")):
                continue
            parts = line.split()
            if len(parts) >= 2:
                cols.append({"name": parts[0], "type": parts[1],
                             "constraints": " ".join(parts[2:])})
        pk = re.findall(r"PRIMARY KEY\s*\(([^)]*)\)", body)
        inline_pk = [c["name"] for c in cols if "PRIMARY KEY" in c["constraints"].upper()]
        tables[name] = {"module": rel, "columns": cols,
                        "primary_key": inline_pk or ([p.strip() for p in pk[0].split(",")] if pk else []),
                        "uniques": re.findall(r"UNIQUE\(([^)]*)\)", body)}
# players table has its own formatting (single-quoted SQL string)
m = re.search(r'CREATE TABLE IF NOT EXISTS players \((.*?)"""\)', MODULES["src/x2server/player/store.py"], re.S)
if m and "players" not in tables:
    body = m.group(1)
    cols = []
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY", "UNIQUE", "CHECK")):
            continue
        parts = line.split()
        if len(parts) >= 2:
            cols.append({"name": parts[0], "type": parts[1], "constraints": " ".join(parts[2:])})
    tables["players"] = {"module": "src/x2server/player/store.py", "columns": cols,
                         "primary_key": [c["name"] for c in cols if "PRIMARY KEY" in c["constraints"].upper()],
                         "uniques": []}

catalog = {"generated_by": "tools/analysis/audit_persistence.py",
           "db_version": "PRAGMA user_version=1",
           "table_count": len(tables), "tables": tables}

# ---------- 2. lifecycle ----------
def fn_of(src, pos):
    """Name of the enclosing top-level def for a source offset."""
    return sorted((sm.group(1), sm.start()) for sm in re.finditer(r"def (\w+)\(", src)
                  if sm.start() < pos)[-1][0]

lifecycle = []
for name, info in sorted(tables.items()):
    writes, reads = [], []
    for rel, src in MODULES.items():
        for m in re.finditer(rf'(?:INSERT(?: OR \w+)?|REPLACE) INTO {name}\b|UPDATE {name}\b SET', src):
            writes.append(f"{rel}:{fn_of(src, m.start())}")
        for m in re.finditer(rf'FROM {name}\b', src):
            reads.append(f"{rel}:{fn_of(src, m.start())}")
    module = info["module"]
    src = MODULES.get(module, "")
    pushes = sorted(set(re.findall(r'OutboundMessage\("(L2C_\w+|PlayerDataProto)"', src)))
    # login restore: does login.py call into the module for this data?
    login_src = MODULES["src/x2server/player/login.py"]
    login_reads = [r for r in reads if "login" in r.split(":")[0]]
    restored_by = sorted({r for r in reads if r.endswith("login_event") or "values" in r or "login" in r})
    has_receipt_like = bool(re.search(r"receipt|digest|uuid", name, re.I)) or "digest" in str(info)
    idempotent = "yes" if has_receipt_like or "PRIMARY KEY" in str(info) else "unknown"
    lifecycle.append({
        "entity": name,
        "module": module,
        "writers": sorted(set(writes)),
        "readers_sample": sorted(set(reads))[:8],
        "push_messages_in_module": pushes,
        "transactional": "yes" if re.search(r"with (self\.)?store\.db|with self\.db", MODULES[module]) else "unknown",
        "idempotent": idempotent,
        "relogin_restore": ("RESTORED_AT_LOGIN" if restored_by or name == "players"
                            else ("QUERY_ONLY" if reads else "PERSISTED_NOT_RESTORED")),
        "pk": info["primary_key"],
    })

state = {"generated_by": "tools/analysis/audit_persistence.py",
         "note": "writers/readers resolved from static grep of src/x2server; "
                 "relogin_restore is inferred from whether login-time assembly reads the table",
         "snapshot_entities": ["gold", "crystal", "exp", "hero_exp", "equip_exp", "daily_activity",
                               "week_activity", "main_chapter", "main_section", "mobility.power",
                               "heroes[id,level,star,state,skills,god_equip]", "show", "nickname"],
         "snapshot_restore": "PlayerDataProto.snapshot_push reads the full snapshot at every login "
                             "(src/x2server/player/login.py:64-85)",
         "lifecycle": lifecycle}
(OUT / "sqlite_schema_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
(OUT / "state_lifecycle.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")

# ---------- 3. markdown ----------
lines = ["# SQLite / Repository / 持久化 / 重登 审计", "",
         f"静态解析 `src/x2server`（未打开活跃库）。共 {len(tables)} 张表。机器可读："
         "`analysis/persistence/sqlite_schema_catalog.json` 与 `state_lifecycle.json`。", "",
         "| 表 | 模块 | 主键 | 写入函数 | 事务 | 幂等 | 重登恢复 | 模块内 push |",
         "|---|---|---|---|---|---|---|---|"]
for e in lifecycle:
    lines.append(f"| {e['entity']} | {e['module'].split('/')[-1]} | {','.join(e['pk']) or '—'} "
                 f"| {len(e['writers'])} | {e['transactional']} | {e['idempotent']} "
                 f"| {e['relogin_restore']} | {','.join(e['push_messages_in_module'][:3]) or '—'} |")
lines += ["", "## Snapshot 实体（players.snapshot JSON）", "",
          "全部账号级状态（gold/crystal/exp/hero_exp/equip_exp/日周活跃/main_chapter/main_section/"
          "mobility/heroes 数组）存于 `players.snapshot`，每次登录经 `snapshot_push` 全量回送"
          "（login.py:64-85）；写入走 `save_snapshot` 乐观并发校验（revision 冲突回滚）。", "",
          "## 风险标注", ""]
not_restored = [e for e in lifecycle if e["relogin_restore"] == "PERSISTED_NOT_RESTORED"]
volatile = [e for e in lifecycle if e["relogin_restore"] == "QUERY_ONLY"]
if not_restored:
    lines += ["### PERSISTED_NOT_RESTORED", ""] + [f"- `{e['entity']}`（{e['module']}）" for e in not_restored] + [""]
if volatile:
    lines += ["### QUERY_ONLY（登录不回送，仅查询时读取）", ""] + [f"- `{e['entity']}`" for e in volatile] + [""]
lines += ["### 其他已知边界（引用既有报告）", "",
          "- battle profile / CheckFightProfile 固定不存在（runtime_coverage_matrix I 域 STUB）。",
          "- Guide/Mail/Achievement/Shop/Activity/Friend/Club 无状态表——客户端请求这些域时无持久化。",
          "- pending_rewards 是待发账本：只登记不自动入包（NEED.md）。", ""]
(REPO / "docs" / "persistence_relog_audit.md").write_text("\n".join(lines), encoding="utf-8")
print(f"tables: {len(tables)}; lifecycle entries: {len(lifecycle)}")
print("not restored:", [e['entity'] for e in not_restored])
print("query only:", [e['entity'] for e in volatile])
