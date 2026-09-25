"""PART B: global ID namespace + reference graph + reverse reference index.

Outputs:
  analysis/static_dictionary/id_namespaces.json
  analysis/static_dictionary/reference_graph.json
  analysis/static_dictionary/reverse_reference_index.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _table_common import (CODE_CONFIRMED, NAMESPACE_SPECS, REJECTED,
                           build_namespace_sets, iter_values,
                           load_decoded_tables, load_registry)

OUT = REPO / "analysis" / "static_dictionary"
OUT.mkdir(parents=True, exist_ok=True)

tables = load_decoded_tables()
ns = build_namespace_sets(tables)

# ---- id_namespaces.json ----
id_namespaces = {
    "generated_by": "tools/analysis/build_reference_graph.py",
    "namespaces": {
        k: {"table": v["table"], "pk_field": v["field"], "count": v["count"],
            "min": v["values"][0], "max": v["values"][-1]}
        for k, v in sorted(ns.items())},
}
(OUT / "id_namespaces.json").write_text(json.dumps(id_namespaces, ensure_ascii=False, indent=1),
                                        encoding="utf-8")

ns_values = {k: set(v["values"]) for k, v in ns.items()}

def field_values(records, field, limit=40000):
    vals = Counter()
    for r in records[:limit]:
        v = r.get(field)
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, int):
            vals[v] += 1
        elif isinstance(v, list):
            for x in v:
                if isinstance(x, int) and not isinstance(x, bool):
                    vals[x] += 1
                elif isinstance(x, dict):
                    for y in iter_values(x):
                        vals[y] += 1
        elif isinstance(v, dict):
            for y in iter_values(v):
                vals[y] += 1
    return vals

# name hints: source field contains target namespace keyword
HINTS = {
    "Section": ("section",), "Chapter": ("chapter",), "Scene": ("scene",),
    "Map": ("map", "sceneid"), "Unit": ("unit", "monster",), "Item": ("item",),
    "Gift": ("gift", "reward", "award"), "DropClass": ("drop", "droop", "dc"),
    "CurrencyType": ("currency", "resource"), "NpcEvent": ("npcevent", "npceventid"),
    "Quest": ("quest",), "MonsterEventGroup": ("eventgroup", "monsterevent"),
    "MonsterEventTable": ("monsterevent",), "Skill": ("skill",),
    "Artifact": ("artifact", "weapen", "weapon"), "Hero": ("hero", "heroid"),
    "DailyDungeon": ("dungeon",), "WeeklyDungeon": ("dungeon",),
    "Shop": ("shopid", "shop"), "Goods": ("goods", "quickbuy"), "ShopGroup": ("shopgroup", "goodsgroup"),
    "FunctionOpen": ("function",), "TitoGuide": ("guide", "tito"),
    "Achievement": ("achievementid", "achievement"), "TaskCondition": ("condition",),
    "DailyTask": ("dailytask",), "Mission": ("mission",),
    "WorldBoss": ("worldboss", "boss"), "Tower": ("towerid", "tower"),
    "PassiveSpell": ("passive",), "ExtraDroop": ("extradroop", "droop"),
    "Jump": ("jump",), "LanguageKey": ("langue", "language", "name", "desc", "text"),
}

# collect (table, field) -> value counter for all int-ish fields
all_fields = {}
for tname, recs in tables.items():
    if not recs:
        continue
    seen_fields = set()
    for r in recs[:200]:
        seen_fields.update(r.keys())
    for f in sorted(seen_fields):
        cnt = field_values(recs, f)
        if len(cnt) >= 3:
            all_fields[(tname, f)] = cnt

print(f"scanning {len(all_fields)} (table, field) pairs against {len(ns_values)} namespaces")

# small-value namespaces that collide with arbitrary counters; require a
# specific name token before allowing anything above WEAK
COLLISION_PRONE = {"ShopGroup", "Shop", "Goods", "Tower", "DailyTask",
                   "ExtraDroop", "PassiveSpell", "FunctionOpen", "TitoGuide",
                   "Achievement", "Jump", "NpcEvent", "Mission"}

relations = []
reverse = defaultdict(lambda: defaultdict(set))  # ns -> value -> {(table, field)}
for (tname, f), cnt in all_fields.items():
    distinct = set(cnt)
    if len(distinct) < 3:
        continue
    best_per_ns = []
    for nsname, nsvals in ns_values.items():
        if tname == ns[nsname]["table"] and f == ns[nsname]["field"]:
            continue  # self pk
        inter = distinct & nsvals
        if len(inter) < 3:
            continue
        cov = len(inter) / len(distinct)
        fkey = f.lower().replace("_", "")
        specific_hit = (nsname.lower() in fkey
                        or any(h in fkey for h in HINTS.get(nsname, ())))
        if nsname in COLLISION_PRONE and not specific_hit:
            continue
        best_per_ns.append((nsname, len(inter), round(cov, 3), specific_hit))
    best_per_ns.sort(key=lambda x: (-x[2], -x[1]))
    for nsname, inter_n, cov, name_hit in best_per_ns[:3]:
        if cov < 0.3 and not name_hit:
            continue
        if cov >= 0.9 and name_hit:
            conf = "CONFIRMED"
        elif cov >= 0.9 or (cov >= 0.5 and name_hit):
            conf = "STRONG"
        else:
            conf = "WEAK"
        relations.append({
            "source_table": tname, "source_field": f, "target_namespace": nsname,
            "target_table": ns[nsname]["table"], "target_field": ns[nsname]["field"],
            "intersection": inter_n, "distinct": len(distinct),
            "coverage": cov, "name_hint": name_hit, "confidence": conf,
            "evidence": "value-domain intersection" + (" + field-name match" if name_hit else ""),
        })
        if conf in ("CONFIRMED", "STRONG"):
            for v in distinct & ns_values[nsname]:
                reverse[nsname][v].add(f"{tname}.{f}")

# upgrade code-confirmed
conf_keys = {(s, f, n) for s, f, n, _ in CODE_CONFIRMED}
for rel in relations:
    if (rel["source_table"], rel["source_field"], rel["target_namespace"]) in conf_keys:
        rel["confidence"] = "CONFIRMED"
        rel["evidence"] = next(e for s, f, n, e in CODE_CONFIRMED
                               if (s, f, n) == (rel["source_table"], rel["source_field"], rel["target_namespace"]))
# ensure code-confirmed relations exist even if scan missed them
existing = {(r["source_table"], r["source_field"], r["target_namespace"]) for r in relations}
for s, f, n, ev in CODE_CONFIRMED:
    if (s, f, n) not in existing and (s, f) in all_fields:
        cnt = all_fields[(s, f)]
        distinct = set(cnt)
        inter = distinct & ns_values.get(n, set())
        relations.append({
            "source_table": s, "source_field": f, "target_namespace": n,
            "target_table": ns[n]["table"] if n in ns else "?", "target_field": ns[n]["field"] if n in ns else "?",
            "intersection": len(inter), "distinct": len(distinct),
            "coverage": round(len(inter) / len(distinct), 3) if distinct else 0,
            "name_hint": True, "confidence": "CONFIRMED", "evidence": ev,
        })
        for v in inter:
            reverse[n][v].add(f"{s}.{f}")

# rejected relations
rejected_out = []
for s, f, n, ev in REJECTED:
    cnt = all_fields.get((s, f))
    inter = len(set(cnt) & ns_values[n]) if cnt else 0
    rejected_out.append({"source_table": s, "source_field": f, "target_namespace": n,
                         "intersection": inter, "evidence": ev})

relations.sort(key=lambda r: (r["confidence"], -r["coverage"]))
conf_counter = Counter(r["confidence"] for r in relations)
print("relation confidence:", dict(conf_counter))

reference_graph = {
    "generated_by": "tools/analysis/build_reference_graph.py",
    "relation_count": len(relations),
    "confidence_counts": dict(conf_counter),
    "relations": relations,
    "rejected_relations": rejected_out,
}
(OUT / "reference_graph.json").write_text(json.dumps(reference_graph, ensure_ascii=False), encoding="utf-8")

reverse_out = {n: {str(v): sorted(refs) for v, refs in sorted(m.items(), key=lambda x: -len(x[1]))}
               for n, m in reverse.items()}
rev_meta = {"generated_by": "tools/analysis/build_reference_graph.py",
            "namespaces_indexed": {n: len(m) for n, m in reverse_out.items()},
            "note": "value -> referencing table.field sets (CONFIRMED/STRONG relations only)",
            "index": reverse_out}
(OUT / "reverse_reference_index.json").write_text(json.dumps(rev_meta, ensure_ascii=False), encoding="utf-8")

top = [r for r in relations if r["confidence"] == "CONFIRMED"]
print(f"CONFIRMED relations: {len(top)}")
for r in top[:25]:
    print(f"  {r['source_table']}.{r['source_field']} -> {r['target_namespace']} ({r['coverage']})")
