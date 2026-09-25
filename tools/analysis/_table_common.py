"""Shared loader for the static-table dictionary / reference-graph scripts.

Reads the APK-derived decodes in D:/demo/x2/analysis/drop_archaeology/
(read-only) plus dump.cs schemas. Deterministic; no network, no APK writes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

X2_ROOT = Path(r"D:\demo\x2")
REPO = X2_ROOT / "x2_revive_workspace"
DROPOUT = X2_ROOT / "analysis" / "drop_archaeology"

if str(X2_ROOT) not in sys.path:
    sys.path.insert(0, str(X2_ROOT))

# Primary-key field per namespace (curated from decode evidence).
# namespace name -> (table_file_stem, pk_field)
NAMESPACE_SPECS = {
    "Section": ("sectiontable", "SectionID"),
    "Chapter": ("chapterinfo", "ChapterID"),
    "Scene": ("scenebase", "ID"),
    "Map": ("mapinfo", "MapTypeID"),
    "Unit": ("unitbase", "ID"),
    "Item": ("item", "ItemID"),
    "Gift": ("gift", "GiftGroup"),
    "DropClass": ("dropprop", "DropClass"),
    "CurrencyType": ("currencytype", "TpyeId"),
    "NpcEvent": ("npcevent", "NPCEventID"),
    "Quest": ("quest", "QuestID"),
    "MonsterEventGroup": ("monstereventgroup", "EventGroupID"),
    "MonsterEventTable": ("monstereventtable", "EventID"),
    "Skill": ("skillbase", "ID"),
    "Artifact": ("artifactbase", "ArtifactID"),
    "Hero": ("playerattrib", "ID"),
    "DailyDungeon": ("dailydungeon", "ID"),
    "WeeklyDungeon": ("weeklydungeon", "ID"),
    "Shop": ("shopconfig", "ShopID"),
    "Goods": ("shopgoodsgroup", "GoodsID"),
    "ShopGroup": ("shopgoodsgroup", "GroupID"),
    "FunctionOpen": ("functionopen", "ID"),
    "TitoGuide": ("titoguidetable", "ID"),
    "Achievement": ("achievement", "AchievementID"),
    "TaskCondition": ("taskcondition", "TaskConditionID"),
    "DailyTask": ("dailytask", "DailyTaskID"),
    "Mission": ("missiontable", "MissionID"),
    "WorldBoss": ("worldbossinfo", "BossID"),
    "Tower": ("towerbase", "TowerID"),
    "PassiveSpell": ("passivespelltb", "PassiveID"),
    "ExtraDroop": ("extradroop", "ID"),
    "Jump": ("jump", "ID"),
    "LanguageKey": ("language", "Key"),
}

# Relations already confirmed by code-level evidence in earlier rounds.
# (source_table, source_field, target_namespace, evidence)
CODE_CONFIRMED = [
    ("sectiontable", "Maps", "Scene", "phase3: Section.Maps -> SceneBase.ID 3191/3203"),
    ("sectiontable", "Maps", "Map", "phase3: Section.Maps -> MapInfo.MapTypeID 3202/3203"),
    ("sectiontable", "VReward", "Gift", "economy audit: 4521/4521 Gift hits"),
    ("sectiontable", "FirVReward", "Gift", "economy audit: 941/941 Gift hits"),
    ("sectiontable", "MopReward", "Gift", "economy audit: 149/149 Gift hits"),
    ("gift", "GiftValue", "Item", "economy audit: 28016/28220 Item hits"),
    ("unitbase", "DC", "DropClass", "archaeology: 494 units, 62 distinct, 100% DropClass"),
    ("unitbase", "SKill", "Skill", "phase3: 4017/4020 hits"),
    ("currencytype", "ItemID", "Item", "archaeology: 901->1237901 etc."),
    ("dailydungeon", "SectionID", "Section", "economy audit: 141/147 E_Daily linked"),
    ("extradroop", "SectionGroup", "Section", "archaeology: 2130101-105 bound"),
    ("extradroop", "ExtraParam1", "Item", "archaeology: 1237901 / 1238100-105"),
    ("playerattrib", "WeapenId", "Artifact", "progression audit: 1503->ArtifactBase"),
    ("playerattrib", "ChipPropID", "Item", "progression audit: 1201003"),
    ("dailytask", "TaskConditionID", "TaskCondition", "economy audit: 40/40"),
    ("dailytask", "GiftGroup", "Gift", "economy audit: 40/40"),
    ("achievement", "AchievementConditionID", "TaskCondition", "name+economy audit cross"),
    ("npcevent", "NPCEventID", "NpcEvent", "self domain"),
    ("shopconfig", "GoodsGroupId", "ShopGroup", "economy audit: 610/610"),
    ("shopgoodsgroup", "GoodsID", "Goods", "self domain"),
]

# Relations explicitly falsified (negative results to keep).
REJECTED = [
    ("sectiontable", "DropValueID", "DropClass",
     "deep_drop_archaeology: 341 values, 0 hits in DropProp or any other table"),
    ("sectiontable", "DropValueID", "Item",
     "deep_drop_archaeology: intersection 0"),
    ("sectiontable", "DropValueID", "Gift",
     "deep_drop_archaeology: intersection 0"),
    ("sectiontable", "DropValueID", "Scene",
     "deep_drop_archaeology: intersection 0"),
]


def load_registry():
    return json.loads((DROPOUT / "table_registry_extract.json").read_text(encoding="utf-8"))


def load_decoded_tables():
    tables = {}
    for f in sorted((DROPOUT / "full_tables").glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        tables[f.stem] = d["records"]
    return tables


def build_namespace_sets(tables):
    """namespace -> sorted list of PK values + meta."""
    ns = {}
    for name, (stem, field) in NAMESPACE_SPECS.items():
        recs = tables.get(stem)
        if not recs:
            continue
        vals = set()
        for r in recs:
            v = r.get(field)
            if isinstance(v, bool):
                continue
            if isinstance(v, int) and v:
                vals.add(v)
            elif isinstance(v, list):
                vals.update(x for x in v if isinstance(x, int) and x)
        if vals:
            ns[name] = {"table": stem, "field": field, "count": len(vals),
                        "values": sorted(vals)}
    return ns


def iter_values(node):
    """Yield every int in a decoded structure (not bool)."""
    if isinstance(node, bool):
        return
    if isinstance(node, int):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from iter_values(v)
    elif isinstance(node, list):
        for v in node:
            yield from iter_values(v)


def field_paths(records):
    """All leaf field paths (top-level key + nested list/dict markers collapsed)."""
    paths = set()
    def walk(node, prefix):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{prefix}.{k}" if prefix else k)
        elif isinstance(node, list):
            if node and all(isinstance(x, (int, float)) for x in node):
                paths.add(prefix)
            else:
                for v in node[:3]:
                    walk(v, prefix)
        else:
            paths.add(prefix)
    for r in records[:50]:
        walk(r, "")
    return sorted(paths)
