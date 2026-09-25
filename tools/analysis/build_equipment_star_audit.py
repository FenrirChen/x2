"""Equipment star-encoding audit + initial affix semantics — deliverable generator.

Outputs analysis/equipment/:
  equipment_id_matrix.csv, equipment_star_exceptions.json, hero_equip_star_consumers.json,
  equip_param_slot_consumers.json, minor_count_xrefs.json, equib_stage_xrefs.json,
  initial_equipment_samples.json
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
X2 = REPO.parent
FT = X2 / "analysis/drop_archaeology/full_tables"
OUT = REPO / "analysis" / "equipment"
OUT.mkdir(parents=True, exist_ok=True)

def load(n):
    return json.loads((FT / f"{n}.json").read_text(encoding="utf-8"))["records"]

items = {i["ItemID"]: i for i in load("item")}
lang = {r["Key"]: r.get("Chinese") for r in load("language")}
eb = {e["EquibId"]: e for e in load("equibbase")}
es_rows = load("equibstage")
bd_rows = load("equibattribbd")

# ---------- equipment_id_matrix.csv ----------
rows = []
exceptions = []
for iid in sorted(items):
    it = items[iid]
    if not (isinstance(it.get("ItemType"), dict) and it["ItemType"]["enum"] == "E_Equip"):
        continue
    name = lang.get(it.get("NameID"), "")
    base = eb.get(iid)
    family = "PART_LEVEL(1240)" if str(iid).startswith("1240") else "SET_STAR(1245)"
    suit = part = star_from_id = None
    if base:
        suit, part = base["EquibSuit"], base["EquibPart"]
    if family == "SET_STAR(1245)":
        star_from_id = iid % 10          # last digit encodes star
        set_index = (iid // 10) % 100    # suit ordinal within 1245 family
        suit = 400 + set_index
        part = None                      # set-level: no part
    q = (it.get("ItemQuality") or {}).get("enum")
    star_in_name = None
    import re
    m = re.search(r"(\d)★", name or "")
    if m:
        star_in_name = int(m.group(1))
    notes = ""
    if family == "PART_LEVEL(1240)" and star_in_name is not None:
        notes = "name contains N★ — verify (part-level items usually use ·一~·六 part markers)"
    if base is None and family == "PART_LEVEL(1240)":
        notes = "no EquibBase row"
    rows.append({
        "item_id": iid, "name": name, "set_name": (name or "").replace(f"{star_in_name}★", "") if star_in_name else name,
        "equib_suit": suit, "part": part, "star_static": star_from_id,
        "quality_static": q, "equib_base_id": iid if base else "",
        "item_type": "E_Equip", "related_stage": star_from_id,
        "im_quality_level": it.get("IMQualityLevel"), "item_value": it.get("ItemValue"),
        "star_in_name": star_in_name, "family": family, "notes": notes,
    })
    # exception bookkeeping
    if family == "PART_LEVEL(1240)" and base is None:
        exceptions.append({"item_id": iid, "kind": "PART_LEVEL_ITEM_WITHOUT_EQUIBBASE", "name": name})
for eid, e in sorted(eb.items()):
    if eid not in items:
        exceptions.append({"equib_base_id": eid, "kind": "EQUIBBASE_ROW_WITHOUT_ITEM",
                           "suit": e["EquibSuit"], "part": e["EquibPart"]})

with (OUT / "equipment_id_matrix.csv").open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)

# ---------- grouping stats (A2) ----------
groups = defaultdict(dict)
for r in rows:
    if r["family"] == "SET_STAR(1245)":
        groups[(r["equib_suit"], "set")][r["star_static"]] = r["item_id"]
full = sum(1 for g in groups.values() if set(g) == {1, 2, 3, 4, 5, 6})
partial = {k: sorted(v) for k, v in groups.items() if set(v) != {1, 2, 3, 4, 5, 6}}
part_groups = defaultdict(list)
for r in rows:
    if r["family"] == "PART_LEVEL(1240)":
        part_groups[(r["equib_suit"], r["part"])].append(r["item_id"])

# last-digit vs star stats (A3)
last_digit_stats = {
    "part_level_1240_last_digit_is_PART": True,
    "part_level_last_digit_distribution": dict(sorted(Counter(i % 10 for i in items if str(i).startswith("1240") and items[i].get("ItemType", {}).get("enum") == "E_Equip").items())),
    "set_star_1245_last_digit_distribution": dict(sorted(Counter(i % 10 for i in items if str(i).startswith("1245") and items[i].get("ItemType", {}).get("enum") == "E_Equip").items())),
    "set_star_name_crosscheck": {
        "named_star_items": sum(1 for r in rows if r["star_in_name"]),
        "name_star_equals_last_digit": all(
            r["star_in_name"] == r["star_static"] for r in rows if r["star_in_name"] is not None),
    },
}

# ---------- EquibStage / EquibAttribBD consistency (B4/B10) ----------
stage_table = {r["Stage"]: {"MinorListMin": r["MinorListMin"], "MinorListMax": r["MinorListMax"],
                            "EquibValue": r.get("EquibValue")} for r in es_rows}
bd_by_star = defaultdict(list)
for r in bd_rows:
    if r.get("EquibQuality"):
        v=r.get("MinorAttrNum")
        if v is not None: bd_by_star[r["EquibQuality"]].append(v)
bd_summary = {q: {"rows": len(v), "MinorAttrNum_values": sorted(set(v))} for q, v in sorted(bd_by_star.items(), key=lambda kv: (kv[0] is None, kv[0]))}
consistency = []
for star in range(1, 7):
    st = stage_table.get(star, {})
    bd = bd_summary.get(star, {})
    lo, hi = st.get("MinorListMin"), st.get("MinorListMax")
    vals = [x for x in bd.get("MinorAttrNum_values", []) if x is not None]
    ok = (vals and lo is not None and min(vals) >= lo and max(vals) <= (hi if hi is not None else lo))
    consistency.append({"star": star, "EquibStage_Min": lo, "EquibStage_Max": hi,
                        "AttribBD_MinorAttrNum_values": vals,
                        "attribBD_within_stage_range": bool(ok)})

# ---------- JSON deliverables ----------
json.dump({
    "verdict": "MODEL C → refined: part-level instance TypeId (1240|SS|P) does NOT encode star "
               "(last digit = part 1-6); the 1245|SS|S family encodes (suit, star) but is a "
               "set-level display/collection family with no part and no EquibBase row, so it cannot "
               "be an instance TypeId; HeroEquip.Star is an independent server-provided instance field",
    "families": {
        "PART_LEVEL(1240)": {"items": 108, "encoding": "1240|SS|P — SS=suit ordinal(00-19), P=part(1-6)",
                              "equib_base_rows": 108, "star_in_id": False},
        "SET_STAR(1245)": {"items": 120, "encoding": "1245|SS|S — SS=suit ordinal(00-19), S=star(1-6)",
                            "equib_base_rows": 0, "star_in_id": True,
                            "quality_progression": "E_White/Green/Blue/Purple/Orange/Red == star 1-6",
                            "observed_in": ["SectionTable.DroopDisplay (64 refs) — 掉落展示/图鉴"]}},
    "groups": {
        "set_star_groups_total": len(groups), "full_1_to_6_star_groups": full,
        "partial_groups": partial,
        "part_level_groups": len(part_groups)},
    "last_digit_stats": last_digit_stats,
    "exceptions": exceptions,
}, (OUT / "equipment_star_exceptions.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)

json.dump({
    "HeroEquip.Star offset": "0x20 (PlayerDbData.HeroEquip)",
    "readers": [
        {"method": "EquipStrengthWnd.CheckSubAttruib(HeroEquip)", "rva": "0x1C30CFC",
         "use": "star -> EquibStageManager.GetItem(star) -> MinorListMax gate for strengthen-added affixes (A)"},
        {"method": "EquipStrengthWnd.SetStrengthInfo", "rva": "0x1C2EDFC",
         "use": "strength window display (GetAttrNum + EquibStage) (A)"},
        {"method": "BagModule/BagMainPage/* (18 sites via EquibBaseManager.GetItem)",
         "use": "TypeId -> EquibBase for part/suit/attrs — TypeId keys EquibBase, NOT star (A)"}],
    "writers": [
        {"finding": "NO local HeroEquip.Star assignment found anywhere",
         "evidence": "GMMainPage.GetEquip (0x13A1F1C) validates (equipId vs EquibBase) and "
                     "(star-key vs EquibAttribBD) then sends C2L_Cheat{opt=15, values=[equipId, attrbdId]} — "
                     "the SERVER builds instances; no HeroEquip ctor exists client-side (A)"}],
    "conclusion": "client trusts wire Star; no Star=static(TypeId) derivation exists; "
                  "Star and TypeId are independent inputs (GM sends both separately)",
}, (OUT / "hero_equip_star_consumers.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)

json.dump({
    "EquipParam layout": {"At1/Av1 (0x10/0x14)": "MAIN attribute slot",
                           "At2..At6/Av2..Av6 (0x18..0x3C)": "minor affix slots (max 5)",
                           "Lock1..Lock6 (0x40..0x54)": "per-slot lock flags"},
    "counting_rule": {
        "method": "EquipStrengthWnd.GetAttrNum(HeroEquip) @ 0x1C30E28 (A: full disasm)",
        "rule": "count = number of NONZERO Av among Av2..Av6 (main slot Av1 NOT counted)",
        "pseudocode": "int n=0; foreach av in {Av2,Av3,Av4,Av5,Av6}: n += (av != 0); return n;"},
    "slot_consumers": [
        {"method": "EquipStrengthWnd.CheckSubAttruib", "rva": "0x1C30CFC",
         "flow": "EquibExp.GetItem(level+1).IsEvent==1 (+3/6/9/12/15) -> EquibStage[Star].MinorListMax "
                 "vs GetAttrNum(equip) -> whether this strengthen ADDS a new affix"},
        {"method": "EquipStrengthWnd.SetStrengthInfo", "rva": "0x1C2EDFC",
         "flow": "display current affixes vs star cap (GetAttrNum + EquibStage.GetItem)"},
        {"method": "ClientProperty.AddEqtsAttributes", "rva": "0x1491674",
         "flow": "agggregates equipped Param slots into player attributes"}],
}, (OUT / "equip_param_slot_consumers.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)

json.dump({
    "minor_count_rule": {
        "EquibStage (keyed Stage=star 1-6)": stage_table,
        "EquibAttribBD (EquibQuality=star)": bd_summary,
        "consistency_check": consistency,
        "verdict": "A-level: two independent static tables agree — initial minor affix count "
                   "is determined by star: 1★=1, 2★=2, 3★=3, 4★=3(→4 after events), 5★=4(→5), 6★=4(→5)"},
    "xrefs": {
        "EquibStageManager.GetItem (7 BL sites)": {
            "LogicX2.DropItemManager.JudgeDropItem": "battle drop gate — reads star/quality-keyed EquibStage (EquibValue) for drop value/quality computation (A)",
            "LogicX2.DropItemManager.SetCurItemValueTotal": "drop value accumulation (A)",
            "EquipStrengthWnd.CheckSubAttruib/SetStrengthInfo": "affix count gates (A)",
            "BagDecomposePage.RefreshCurrency": "decompose value display (A)",
            "CollegePurifyOptTab.RefreshContent": "college purify UI (A)"}},
    "equib_attribBD_xrefs": {
        "EquibAttribBDManager.GetItem (2 BL sites)": ["GMMainPage.GetEquip", "GMMainPage.OnMailGetEquipBtnClick"],
        "note": "GM gives (equipId, attrbdId) to the server; AttribBD rows carry MinorAttrNum + "
                "MinorAttrType[5]/Value[5] pools + StreNum/StreValue — the official roll inputs"},
}, (OUT / "minor_count_xrefs.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)

json.dump({
    "EquibStageManager.GetItem consumers (7)": {
        "0x1E49D90": "LogicX2.DropItemManager.JudgeDropItem — equib drop value/quality path",
        "0x1E4AF00": "LogicX2.DropItemManager.SetCurItemValueTotal",
        "0x1C30DE8": "EquipStrengthWnd.CheckSubAttruib (affix gate)",
        "0x1C2EFA8/0x1C2F354": "EquipStrengthWnd.SetStrengthInfo",
        "0x19A5EF0": "BagDecomposePage.RefreshCurrency",
        "0x1B0DA30": "CollegePurifyOptTab.RefreshContent"},
    "field_offsets": {"EquibStage": {"Stage": "0x10", "MinorListMin": "0x14", "MinorListMax": "0x18",
                                      "EquibSeniorChip": "0x20", "Exp": "0x28", "EquibValue": "0x2C",
                                      "ExpBonus": "0x30", "GoldBonus": "0x34"}},
    "semantics_verdict": "MinorListMin = initial minor affix count for that star; "
                         "MinorListMax = cap reachable via strengthen events (+3/6/9/12/15, "
                         "EquibExp.IsEvent==1). NOT an id-range or post-max value (A: "
                         "CheckSubAttruib compares GetAttrNum < MinorListMax to allow additions)",
}, (OUT / "equib_stage_xrefs.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)

# initial samples from repo fixtures (Revival-generated, NOT official)
samples = []
seed_cat = REPO / "analysis/progression/equipment_seed_catalog.json"
if seed_cat.exists():
    sc = json.loads(seed_cat.read_text(encoding="utf-8"))
    rows_ = sc.get("rows", [])[:6]
    for r in rows_:
        samples.append({"source": "REVIVAL_TEST_SEED (not official)", **{k: r.get(k) for k in ("type_id", "star", "part")}})
json.dump({
    "note": "Only Revival-generated test instances exist in this repo (seed catalog/tests); "
            "they cannot prove official rules. No official HeroEquip samples are available "
            "(instances are server-built; none shipped inside the APK).",
    "samples": samples,
    "official_sample_availability": "NONE_IN_CLIENT — HeroEquip instances never ship in the APK; "
                                     "battle drops only carry ItemDataP{id,num,quality}",
    "quality_star_relation": {
        "finding": "for equib drops the client indexes EquibStage with the item's QUALITY "
                   "(JudgeDropItem path) — quality is the star carrier in the drop pipeline",
        "grade": "B (strong reconstruction; exact DropBase threshold mapping to star unresolved)",
    },
}, (OUT / "initial_equipment_samples.json").open("w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("rows:", len(rows), "exceptions:", len(exceptions))
print("full star groups:", full, "partial:", partial)
print("consistency:", json.dumps(consistency, ensure_ascii=False))
