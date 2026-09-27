"""Export client appearance, voice, and icon identities without ownership grants."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLES = ROOT.parent / "analysis/drop_archaeology/full_tables"
EXTERNAL_ICONS = ROOT.parent / "other/9.26 修复包/9.26 修复包/server/src/x2server/data/icon_catalog.json"
OUTPUT = ROOT / "src/x2server/data/appearance_catalog.json"


def table(name):
    return json.loads((TABLES / f"{name}.json").read_text(encoding="utf-8"))


def build():
    appearance, dubbing, item = table("appearance"), table("dubbing"), table("item")
    classification = json.loads(EXTERNAL_ICONS.read_text(encoding="utf-8"))
    items = {row["ItemID"]: row for row in item["records"]}
    heads, scenes = classification["head"], classification["scene"]
    assert heads[0] == 1000001 and set(heads).isdisjoint(scenes)
    assert all(items[i]["ItemType"]["value"] == 22 for i in heads[1:])
    assert all(items[i]["ItemType"]["value"] in (40, 41) for i in scenes)
    voice_heroes = {row["DubbingId"] // 100: row["HeroId"] for row in dubbing["records"]
                   if "HeroId" in row}
    assert len(voice_heroes) == 39
    assert all(row.get("HeroId", voice_heroes[row["DubbingId"] // 100]) ==
               voice_heroes[row["DubbingId"] // 100] for row in dubbing["records"])
    return {"source": "OFFICIAL_CLIENT_STATIC_WITH_VERIFIED_ICON_CLASSIFICATION",
        "source_hashes": {n: d["source_hash"] for n, d in
                          (("appearance", appearance), ("dubbing", dubbing), ("item", item))},
        "appearance": [{"id": r["AppearanceID"], "hero_id": r["HeroID"],
            "acquire": r.get("AcquireCondition", {}).get("enum"),
            "type": r.get("AppearanceType", {}).get("enum"),
            "unit_id": r.get("UnitBaseID", 0)} for r in appearance["records"]],
        "dubbing": [{"id": r["DubbingId"], "hero_id": voice_heroes[r["DubbingId"] // 100],
            "unlock_condition": r.get("UnlockConditions", 0),
            "locked_flag": bool(r.get("Locked"))} for r in dubbing["records"]],
        "head_icons": heads, "scene_icons": scenes, "starter_head_icon": 1000001}


if __name__ == "__main__":
    OUTPUT.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
