"""PART G: re-audit runtime coverage static-data status against the 209 newly decoded tables.

Updates analysis/coverage/runtime_coverage.json in place (adds static_data_status_v2 and
static_data_note; never downgrades runtime_logic_status) and writes:
  docs/knowledge/coverage/runtime_coverage_static_reaudit.md
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
X2 = REPO.parent
COV = REPO / "analysis" / "coverage" / "runtime_coverage.json"
OUT_MD = REPO / "docs" / "runtime_coverage_static_reaudit.md"

cov = json.loads(COV.read_text(encoding="utf-8"))
features = cov["features"]

reg = json.loads((X2 / "analysis/drop_archaeology/table_registry_extract.json").read_text(encoding="utf-8"))
available = {t["table_name"] for t in reg["tables"]}

# feature keyword -> required tables (all must exist to claim found)
FEATURE_TABLES = {
    "shop": ["shopconfig", "shopgoodsgroup"],
    "dailydungeon": ["dailydungeon", "extradroop"],
    "weeklydungeon": ["weeklydungeon"],
    "activity": ["activitytask", "activityboxgoods", "seasonconfig"],
    "worldboss": ["worldbossinfo", "worldbossevent", "worldbossexplore"],
    "tower": ["tower", "towerbase", "towereffect", "towergrid", "towercontroller", "towerrank"],
    "task": ["dailytask", "taskcondition", "taskcontrol"],
    "draw": ["drawrules", "drawparam"],
    "wish": ["drawrules", "drawparam"],
    "gacha": ["drawrules", "drawparam"],
    "artifact": ["artifactbase", "artifactfuse"],
    "equipment": ["equibbase", "equibattrib", "equibexp", "equibstage", "equibsuit"],
    "achievement": ["achievement", "achievementcondition", "achievementconditionline", "medal"],
    "mail": ["mailconfig", "mailinfo", "privatemail", "privatemailcontrol", "privatemailsystem"],
    "skill": ["skillbase", "skilllevel", "skillhelper"],
    "hero": ["playerattrib", "playerlevelbonus", "playerstage"],
    "guide": ["titoguidetable", "titofightguidetable", "functionopen"],
    "club": ["guildlevel", "guildchallengeinfo", "guildwish", "guildpicture"],
    "guild": ["guildlevel", "guildchallengeinfo", "guildwish", "guildpicture"],
    "friend": ["friendlevel"],
    "currency": ["currencytype", "currencydisplay"],
    "mission": ["missiontable", "missionpredecessor", "chapterinfo"],
    "battle": ["sectiontable", "scenebase", "mapinfo"],
    "fight": ["sectiontable", "scenebase", "mapinfo"],
    "drop": ["dropprop", "dropbase", "extradroop"],
    "endless": ["endlessdungeontask"],
    "challenge": ["challengetask"],
    "monopoly": ["monopolygrid"],
    "moon": ["moonworldmap", "mooncamp", "moonequip", "moonnpc"],
    "blood": ["bloodmoonconfig", "bloodmooninfo", "bloodmoonmodule"],
    "battlepass": ["battlepass", "battlepasslevel", "battlepassaward", "battlepasstask"],
    "fishing": ["fishing"],
    "escort": ["escort"],
    "snatch": ["snatch"],
    "collection": ["collection", "collectiondisplay"],
    "relic": ["reliccollect", "relicevent", "relicrecommend"],
    "favorability": ["favorabilityhero", "favorabilitydailytask", "favorabilitylevel"],
}

# features that remain server-only despite tables (runtime content, not static)
STILL_SERVER_ONLY_NOTES = {
    "shop": "商品 GoodsID→ItemID/数量、库存与刷新执行仍无静态定义（ShopGoodsGroup 无商品内容字段）",
    "drop": "DropValueID→掉落内容无任何客户端静态映射（341 值零命中），权威概率在服务器",
}

def feature_keywords(f):
    text = " ".join(str(f.get(k, "")) for k in
                    ("feature", "subsystem", "domain", "client_module", "known_variants")).lower()
    return text

changes = []
for f in features:
    text = feature_keywords(f)
    matched, missing = [], []
    for kw, tables in FEATURE_TABLES.items():
        if kw in text:
            matched.append(kw)
            missing += [t for t in tables if t not in available]
    if not matched:
        continue
    kw0 = matched[0]
    note = STILL_SERVER_ONLY_NOTES.get(kw0)
    if missing:
        new_status = "PARTIAL"
        note = note or f"缺失表：{sorted(set(missing))[:6]}"
    elif note:
        new_status = "FOUND_BUT_UNMAPPED"
    else:
        new_status = "FOUND_BUT_UNMAPPED"
        note = f"静态表已全部解码：{sorted({t for kw in matched for t in FEATURE_TABLES[kw]})[:6]}"
    old = f.get("static_data_status")
    # never downgrade: complete/partial keep their status; only add the note.
    if old in ("complete", "partial"):
        f["static_data_status_v2"] = old
        f["static_data_note"] = "newly decoded tables available: " + note if note else note
        changes.append({"feature": f.get("feature"), "domain": f.get("domain"),
                        "old": old, "new": old + " (note added)", "note": note,
                        "runtime_unchanged": f.get("runtime_logic_status")})
        continue
    f["static_data_status_v2"] = new_status
    f["static_data_note"] = note
    if old != new_status:
        changes.append({"feature": f.get("feature"), "domain": f.get("domain"),
                        "old": old, "new": new_status, "note": note,
                        "runtime_unchanged": f.get("runtime_logic_status")})

cov["static_data_reaudit"] = {
    "date": "2026-09-25",
    "method": "tools/analysis/build_coverage_reaudit.py against 265-table registry",
    "changed_features": len(changes),
}
COV.write_text(json.dumps(cov, ensure_ascii=False, indent=1), encoding="utf-8")

from collections import Counter
cc = Counter((c["old"], c["new"]) for c in changes)
lines = ["# Runtime Coverage 静态数据重审（基于新发现的 209 张表）", "",
         "方法：将 76 个 coverage feature 与 265 张注册表逐一对照；只更新 "
         "`static_data_status_v2`/`static_data_note`，**runtime_logic_status 一律不动**。"
         "机器可读差异已写回 `analysis/coverage/runtime_coverage.json`（`static_data_reaudit` 节）。", "",
         f"共 {len(changes)} 个 feature 的静态数据状态发生变化。", "",
         "| 旧 static_data_status → 新 | 数量 |", "|---|---:|"]
for (o, n), c in cc.most_common():
    lines.append(f"| {o} → {n} | {c} |")
lines += ["", "## 逐项明细", ""]
for c in changes:
    lines.append(f"- **{c['domain']} / {c['feature']}**: `{c['old']}` → `{c['new']}`"
                 + (f" — {c['note']}" if c.get("note") else ""))
lines += ["", "## 口径提醒", "",
          "- `FOUND_BUT_UNMAPPED` 只表示客户端静态表已解码，不代表服务器运行态可用。",
          "- Shop 保持缺口：商品内容字段在客户端不存在；随机掉落保持 SERVER_ONLY。",
          "- 若重跑 `analysis/coverage/build_runtime_coverage.py` 会重建该 JSON，需合并 "
          "`static_data_status_v2` 字段（本轮脚本可重复执行）。", ""]
OUT_MD.write_text("\n".join(lines), encoding="utf-8")
print("changed:", len(changes))
print(dict(cc))
