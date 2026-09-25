"""PART A: build the 265-table static data dictionary.

Outputs:
  analysis/static_dictionary/tables.json
  analysis/static_dictionary/table_domains.json
  docs/client_static_table_dictionary.md
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _table_common import (DROPOUT, build_namespace_sets, field_paths,
                           iter_values, load_decoded_tables, load_registry)

OUT = REPO / "analysis" / "static_dictionary"
OUT.mkdir(parents=True, exist_ok=True)

registry = load_registry()
tables = load_decoded_tables()
reg_by_name = {t["table_name"]: t for t in registry["tables"]}

# schemas from dump.cs (Example classes)
sys.path.insert(0, str(Path(r"D:\demo\x2")))
from phase3_analyze import build_schema  # noqa: E402
dump = (Path(r"D:\demo\x2") / "tools/Il2CppDumper-bin/dump.cs").read_text(encoding="utf-8")
schemas, classes, enums, _ = build_schema(dump)

DOMAIN_RULES = [
    ("Drop", ("drop", "droop", "loot")),
    ("Reward", ("reward", "gift", "welfare", "bonus", "boxgoods", "boxconfig", "racereward")),
    ("Battle", ("fight", "battle", "attack", "buff", "damage", "combo", "passivespell", "effect", "herodamagefactor", "dynamicgrade", "attribtype", "monsterevent", "monsterwave", "monsterlevel", "monster", "npcevent", "unitbase", "profrestraint")),
    ("Mission", ("mission", "section", "chapter", "map", "scene", "quest", "maptrigger", "pov", "memory", "adventurelist", "mazeindepexp")),
    ("DailyDungeon", ("dailydungeon", "weeklydungeon", "activitydungeon", "endless", "dungeon")),
    ("Shop", ("shop", "goods", "recharge", "vip", "tradeactivity", "mazeshop")),
    ("Task", ("task",)),
    ("Achievement", ("achievement", "medal", "collection", "illustration")),
    ("Draw", ("draw", "card")),
    ("Mail", ("mail", "pushmessage", "notice")),
    ("Friend", ("friend", "favorability", "battlefavorability", "sendgift", "callwords", "emoji")),
    ("Guild", ("guild",)),
    ("Chat", ("chat", "bubbletalk", "brinkconversation", "conversation", "dubbing")),
    ("Activity", ("activity", "season", "holiday", "eventnotice", "noticeevent", "simpleactivity", "newyear", "moon", "bloodmoon", "return", "lightyard", "monopoly", "answerconfig", "questionnaire", "sharemessage", "redpackage", "gameactivity", "dairyresource", "essence")),
    ("WorldBoss", ("worldboss",)),
    ("Tower", ("tower",)),
    ("Challenge", ("challenge", "snatch", "escort", "trial")),
    ("Fishing", ("fishing",)),
    ("Guide", ("guide", "functionopen", "jump", "tips", "msgtips")),
    ("Hero", ("hero", "playerattrib", "playerlevel", "playerstage", "starcharts", "unitstyle", "unitenum", "herolable", "skill", "artifact", "godhole", "jewel", "constellation")),
    ("Equipment", ("equib",)),
    ("Inventory", ("item", "indexinfo", "propertychange", "itemsource", "appearance", "decoration", "picture", "recipe")),
    ("Player", ("roleexp", "accountbuff", "san", "device", "statisticalinformation", "namelist")),
    ("Currency", ("currency",)),
    ("Roguelite", ("relic", "miracle", "randomevent", "collectmiracle", "reliccollect", "relicrecommend")),
    ("College", ("college",)),
    ("System", ("globalparamstring", "gmadvanceaccount", "systemsound", "spineanimation", "expression", "live2d", "sensitiveword", "chatcontrol", "optioneffect", "formation", "componentbase", "director", "condtionenum", "actionenum", "functionenum", "language", "elementsynthesis", "eventtable", "answerconfig")),
]

def domains_for(name):
    n = name.lower()
    out = []
    for dom, kws in DOMAIN_RULES:
        if any(n.startswith(k.strip()) or k.strip() in n for k in kws):
            out.append(dom)
    return out or ["Unknown"]

ns_sets = build_namespace_sets(tables)
ns_values = {k: set(v["values"]) for k, v in ns_sets.items()}

def stat_field(records, key):
    ints, listlens, enumnames, strs, nones = [], [], Counter(), [], 0
    for r in records[:20000]:
        v = r.get(key)
        if v is None:
            nones += 1
            continue
        if isinstance(v, bool):
            ints.append(int(v))
        elif isinstance(v, int):
            ints.append(v)
        elif isinstance(v, float):
            ints.append(v)
        elif isinstance(v, list):
            listlens.append(len(v))
            for x in v[:64]:
                if isinstance(x, int) and not isinstance(x, bool):
                    ints.append(x)
                elif isinstance(x, str):
                    strs.append(x)
                elif isinstance(x, dict):
                    e = x.get("enum")
                    if e:
                        enumnames[e] += 1
                    for y in iter_values(x):
                        ints.append(y)
        elif isinstance(v, dict):
            e = v.get("enum")
            if e:
                enumnames[e] += 1
            for y in iter_values(v):
                ints.append(y)
        elif isinstance(v, str):
            strs.append(v)
    stat = {"type": "list" if listlens else ("enum" if enumnames else ("string" if strs and not ints else "int")),
            "distinct": len(set(ints)), "sample": strs[:2] or ints[:3]}
    if ints:
        stat["min"] = min(ints)
        stat["max"] = max(ints)
        stat["zero_ratio"] = round(sum(1 for i in ints if i == 0) / len(ints), 3)
    if listlens:
        stat["list_len_min"] = min(listlens)
        stat["list_len_max"] = max(listlens)
        stat["list_len_avg"] = round(sum(listlens) / len(listlens), 2)
    if enumnames:
        stat["enums"] = dict(enumnames.most_common(12))
    return stat

def ref_candidates(records, paths):
    """value-namespace coverage for int-like fields."""
    out = []
    for p in paths:
        vals = Counter()
        for r in records[:20000]:
            v = r.get(p)
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
        distinct = set(vals)
        if len(distinct) < 4:
            continue
        best = []
        for nsname, nsvals in ns_values.items():
            inter = distinct & nsvals
            if not inter:
                continue
            cov = len(inter) / len(distinct)
            if cov >= 0.4 and len(inter) >= 4:
                best.append({"namespace": nsname, "intersection": len(inter),
                             "coverage": round(cov, 3)})
        best.sort(key=lambda x: (-x["coverage"], -x["intersection"]))
        if best:
            out.append({"field": p, "distinct": len(distinct), "refs": best[:4]})
    return out

table_entries = []
for t in registry["tables"]:
    name = t["table_name"]
    stem = name  # full_tables use lowercase registered name
    recs = tables.get(stem)
    entry = {
        "table_name": name,
        "class_name": t.get("class_name"),
        "manager_class": t.get("manager_class"),
        "registered": True,
        "alt_namespaces": t.get("alt_namespaces", []),
        "previously_extracted": t.get("previously_extracted"),
        "active_source_hash": t.get("active_source_hash"),
        "size_bytes": t.get("size"),
        "parse_status": t.get("parse_status"),
        "declared_count": t.get("declared_count"),
        "record_count": len(recs) if recs is not None else None,
        "business_domains": domains_for(name),
    }
    if recs:
        paths = field_paths(recs)
        entry["fields"] = {p: stat_field(recs, p) for p in paths}
        # primary key candidates: int fields with distinct == record_count
        pks = [p for p, s in entry["fields"].items()
               if s.get("distinct") == len(recs) and s["type"] == "int" and len(recs) > 3]
        entry["primary_key_candidates"] = pks
        entry["reference_candidates"] = ref_candidates(recs, [p for p, s in entry["fields"].items()
                                                              if s["type"] in ("int", "list", "enum")])
    else:
        entry["note"] = t.get("error") or "no Example schema; container parsed only"
    table_entries.append(entry)

tables_json = {"generated_by": "tools/analysis/build_table_dictionary.py",
               "registry_total": len(table_entries),
               "decoded_tables": len(tables),
               "tables": table_entries}
(OUT / "tables.json").write_text(json.dumps(tables_json, ensure_ascii=False), encoding="utf-8")

domains = defaultdict(list)
for e in table_entries:
    for d in e["business_domains"]:
        domains[d].append(e["table_name"])
(OUT / "table_domains.json").write_text(json.dumps(
    {"domains": {k: sorted(v) for k, v in sorted(domains.items())},
     "multi_domain_tables": sorted(e["table_name"] for e in table_entries if len(e["business_domains"]) > 1)},
    ensure_ascii=False, indent=1), encoding="utf-8")

# markdown summary
lines = ["# 客户端静态表数据字典（265 张注册表）", "",
         "来源：ResourceManager 注册表 + APK 原字节解码（`analysis/drop_archaeology/`）。",
         "机器可读全文：`analysis/static_dictionary/tables.json`（每表字段统计/主键候选/引用候选）。", "",
         "| 表 | 记录数 | 域 | 主键候选 | 关键引用 | 状态 |",
         "|---|---:|---|---|---|---|"]
for e in sorted(table_entries, key=lambda x: (x["business_domains"][0], x["table_name"])):
    rc = e["record_count"] if e["record_count"] is not None else e["declared_count"]
    refs = "; ".join(f"{r['field']}→{r['refs'][0]['namespace']}({r['refs'][0]['coverage']})"
                     for r in (e.get("reference_candidates") or [])[:2])
    lines.append(f"| {e['table_name']} | {rc} | {','.join(e['business_domains'][:3])} "
                 f"| {','.join(e.get('primary_key_candidates', [])[:2])} | {refs or '—'} "
                 f"| {e['parse_status']} |")
_tbl_hdr = ("---\nDocument-Type: Current Knowledge\nDomain: Client\nStatus: AUTHORITATIVE\n"
            "Updated: 2026-09-25\nGenerated-By: tools/analysis/build_table_dictionary.py\n---\n\n")
md = _tbl_hdr + "\n".join(lines) + "\n"
(REPO / "docs" / "knowledge" / "client" / "static_table_dictionary.md").write_text(md, encoding="utf-8")

unknown = [e["table_name"] for e in table_entries if e["business_domains"] == ["Unknown"]]

# A4: for no-schema tables, check dump.cs for any case-insensitive class/manager hits
no_schema = [e for e in table_entries if e["parse_status"] in ("PARSED_NO_SCHEMA", "ERROR", "UNKNOWN_CONTAINER")]
a4 = {}
dump_lc = dump.lower()
for e in no_schema:
    n = e["table_name"]
    hits = sorted(set(re.findall(rf"\b(\w*{re.escape(n)}\w*)\b", dump, re.I)))
    mgr = [h for h in hits if h.lower().endswith("manager")]
    a4[n] = {"identifier_hits": hits[:12], "manager_candidates": mgr[:4],
             "classification": "LIKELY" if mgr else ("UNKNOWN" if hits else "NO_CODE_REF")}
    e["a4_no_schema_investigation"] = a4[n]

print(f"tables: {len(table_entries)}; decoded: {len(tables)}; unknown-domain: {len(unknown)}")
print("unknown:", unknown)
print("domains:", {k: len(v) for k, v in sorted(domains.items())})
print("no-schema investigation:")
for n, r in a4.items():
    print(f"  {n}: {r['classification']} managers={r['manager_candidates']} hits={r['identifier_hits'][:6]}")
tables_json["no_schema_investigation"] = a4
(OUT / "tables.json").write_text(json.dumps(tables_json, ensure_ascii=False), encoding="utf-8")
