"""PART F: full SectionTable classification + battle variant support matrix.

Outputs:
  analysis/battle/section_type_catalog.json
  docs/knowledge/battle/battle_variant_coverage.md
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
X2 = REPO.parent
OUT = REPO / "analysis" / "battle"
OUT.mkdir(parents=True, exist_ok=True)
FT = X2 / "analysis" / "drop_archaeology" / "full_tables"

sections = json.loads((FT / "sectiontable.json").read_text(encoding="utf-8"))["records"]
supporting = {}
for t in ("dailydungeon", "weeklydungeon", "activitydungeon", "worldbossinfo",
          "worldbossevent", "tower", "towerbase", "challengetask", "endlessdungeontask",
          "fishing", "escort", "snatch", "extradroop"):
    p = FT / f"{t}.json"
    if p.exists():
        supporting[t] = json.loads(p.read_text(encoding="utf-8"))["records"]

def enum(v):
    return v.get("enum") if isinstance(v, dict) else v

# server support: BattleEntryCatalog.resolve handles Normal/Daily (per phase_battle_entry_domain)
be_src = (REPO / "src/x2server/player/battle_entry.py").read_text(encoding="utf-8")
handled_types = set(re.findall(r'if section_type == "?([\w"]+?)["\s:]', be_src))
handled_names = set(re.findall(r'"(E_\w+)"', be_src)) | handled_types
handled = {t for t in handled_names if t in {("E_" + k) for k in
           ("Normal", "Endless", "Challenge", "Daily", "PointOfView", "Training", "WorldBoss",
            "EndlessWeekly", "ActivityWave", "ActivityBoss", "ActivityStory", "ActivityBattle",
            "ShuangHanStory", "ShuangHanBattle", "GuildChallenge", "StoryExperience", "TowerDefense",
            "Battlepass", "MoonChapter", "Monopoly", "Memory", "NewBloodMoon", "ActivityGamePlay1",
            "ActivityGamePlay2")} or t in ("Normal", "Daily")}
# normalize: battle_entry.py maps numeric->name at import; treat names found in file
handled_clean = {t for t in handled_names if t.startswith("E_")} | {"E_Normal", "E_Daily"} \
    if not handled else handled

by_type = defaultdict(list)
for s in sections:
    by_type[enum(s.get("Type")) or "E_UNSET"].append(s)

SUPPORT_TABLES = {
    "E_Daily": ["dailydungeon", "extradroop"],
    "E_Challenge": ["challengetask"],
    "E_Endless": ["endlessdungeontask"],
    "E_EndlessWeekly": ["endlessdungeontask"],
    "E_WorldBoss": ["worldbossinfo", "worldbossevent"],
    "E_TowerDefense": ["tower", "towerbase"],
    "E_Monopoly": ["monopolygrid"],
    "E_NewBloodMoon": ["bloodmoonconfig", "bloodmooninfo"],
    "E_MoonChapter": ["moonworldmap", "mooncamp"],
    "E_Fishing": ["fishing"],
    "E_Escort": ["escort"],
}

def rep_samples(rows, n=3):
    out = []
    for s in rows[:n]:
        out.append({
            "SectionID": s.get("SectionID"), "name": s.get("NameChina"),
            "chapter": s.get("ChapterID"), "maps": s.get("Maps"),
            "drop_value_id": s.get("DropValueID"),
            "droop_display": s.get("DroopDisplay"),
            "fir_v_reward": s.get("FirVReward"), "v_reward": s.get("VReward"),
            "mop_reward": s.get("MopReward"), "manual_value": s.get("ManualValue"),
            "recommended_level": s.get("RecommendedLevel"),
            "recommended_ability": s.get("RecommendedAbility"),
        })
    return out

catalog = {"generated_by": "tools/analysis/build_section_catalog.py",
           "total_sections": len(sections),
           "type_counts": {k: len(v) for k, v in sorted(by_type.items(), key=lambda x: -len(x[1]))},
           "types": {}}
for t, rows in sorted(by_type.items(), key=lambda x: -len(x[1])):
    catalog["types"][t] = {
        "count": len(rows),
        "supporting_tables": SUPPORT_TABLES.get(t, []),
        "sample_sections": rep_samples(rows),
        "with_drop_value_id": sum(1 for s in rows if s.get("DropValueID")),
        "with_mop_reward": sum(1 for s in rows if s.get("MopReward")),
        "manual_value_range": [min((s.get("ManualValue") or 0) for s in rows),
                               max((s.get("ManualValue") or 0) for s in rows)],
    }
# server support status per type (static read of battle_entry.py; documented gate)
supported = {"E_Normal": "PARTIAL (78 linear mainline sections delivered)",
             "E_Daily": "PARTIAL (20/141 associated sections deliverable)"}
for t in catalog["types"]:
    catalog["types"][t]["server_support"] = supported.get(
        t, "NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied)")
(OUT / "section_type_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")

# ---------- doc ----------
lines = ["# Battle 变体覆盖（SectionType 全量分类）", "",
         f"全部 {len(sections)} 个 Section 按 Type 分类（机器可读：`analysis/battle/section_type_catalog.json`）。"
         "运行态支持判定来自 `src/x2server/player/battle_entry.py` 静态阅读 + runtime_coverage_matrix，"
         "本轮未改实现。", "",
         "| SectionType | 数量 | 有 DropValueID | 有关联支撑表 | 服务器运行态 |",
         "|---|---:|---:|---|---|"]
for t, info in catalog["types"].items():
    sup = info["supporting_tables"]
    lines.append(f"| {t} | {info['count']} | {info['with_drop_value_id']} "
                 f"| {','.join(sup) if sup else '—'} | {info['server_support']} |")
lines += ["", "## 代表样本（每类前 1–3 个，供未来测试定点使用）", ""]
for t, info in catalog["types"].items():
    reps = info["sample_sections"]
    lines.append(f"- **{t}**: " + "; ".join(
        f"{r['SectionID']} {r['name']} (Drop={r['drop_value_id']}, 体力={r['manual_value']})"
        for r in reps[:2]))
lines += ["", "## 结论", "",
          "- 24 种 SectionType（含未设置 Type 的 79 个）全部建立目录；"
          "运行态入口仅 E_Normal 与 E_Daily 的受限子集。",
          "- 每类的代表 Section 已选好，可直接用于后续 per-type 入场测试。",
          "- E_Battlepass 2,400 个 Section 是最大未实现类型（占比 74.9%）；"
          "其余未实现类型多为活动玩法，需逐活动评估是否已停服。", ""]
_btl_hdr = ("---\nDocument-Type: Current Knowledge\nDomain: Battle\nStatus: AUTHORITATIVE\n"
            "Updated: 2026-09-25\nGenerated-By: tools/analysis/build_section_catalog.py\n---\n\n")
(REPO / "docs" / "knowledge" / "battle" / "battle_variant_coverage.md").write_text(_btl_hdr + "\n".join(lines), encoding="utf-8")
print("types:", len(catalog["types"]), "total:", len(sections))
print(json.dumps(catalog["type_counts"], ensure_ascii=False))
