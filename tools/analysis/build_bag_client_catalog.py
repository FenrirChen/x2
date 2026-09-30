"""Export bag use links, gifts and composition recipes from canonical client tables.

Item/Gift/Language inputs are extracted by extract_dp_client_evidence.py.
Recipe/JewelBase use the same APK ResourceManager extraction and strict framing.
"""
import json
import hashlib
import re
from collections import defaultdict
from pathlib import Path

from _client_table_wire import parse_message, parse_table_container

ROOT = Path(__file__).resolve().parents[2]


def table(directory, name):
    parsed = parse_table_container((directory / f"{name}.bytes").read_bytes())
    assert parsed["kind"] == "array" and not parsed["unknown_wrapper_fields"]
    rows = {}
    for key, blob in zip(parsed["keys"], parsed["items"], strict=True):
        values, consumed = parse_message(blob)
        assert consumed == len(blob)
        row = defaultdict(list)
        for value in values:
            row[value.field].append(value.value)
        assert row[1] == [key] and key not in rows
        rows[key] = row
    return rows


def build():
    raw = ROOT / "analysis/dp_client/raw"
    items, gifts, language = (table(raw, n) for n in ("item", "gift", "language"))
    extra = ROOT / "analysis/bag_client/raw"
    if not (extra / "recipe.bytes").exists():
        import extract_dp_client_evidence as extractor
        extractor.TABLES = {"recipe", "jewelbase"}
        extractor.extract(ROOT.parent / "X2_Eclipse_v2_4.apk", extra)
    recipes, jewels = (table(extra, n) for n in ("recipe", "jewelbase"))
    def first(row, field, default=0):
        return row[field][0] if row[field] else default
    def name(row):
        text = language.get(first(row, 2))
        return text[2][0].decode("utf8") if text and text[2] else ""
    links = {str(k): {"used": r[16], "name": name(r)}
             for k, r in items.items() if r[16]}
    for link in links.values():
        match = re.search(r"([1-6])★", link["name"])
        if match:
            link["equipmentStar"] = int(match[1])
        stars = set()
        for group in link["used"]:
            gift = gifts[group]
            if any(first(items[i], 6) == 10 for i in gift[4]):
                for shown in gift[6]:
                    match = re.search(r"([1-6])★", name(items[shown]))
                    if match:
                        stars.add(int(match[1]))
        if stars:
            assert len(stars) == 1
            link["equipmentStar"] = stars.pop()
    groups = {g for r in links.values() for g in r["used"]}
    assert groups <= gifts.keys()
    payload = {
        "provenance": "Canonical 2.4 APK ResourceManager; RSA/XOR decode; strict protobuf framing",
        "sourceSha256": {n: hashlib.sha256((directory / f"{n}.bytes").read_bytes()).hexdigest()
            for directory, names in ((raw, ("item", "gift", "language")), (extra, ("recipe", "jewelbase")))
            for n in names},
        "items": links,
        "gifts": {str(k): {"awardType": first(gifts[k], 2),
            "weights": gifts[k][3], "items": list(zip(gifts[k][4], gifts[k][5], strict=True))}
            for k in sorted(groups)},
        "recipes": {str(k): {"type": first(r, 2),
            "costs": list(zip(r[3], r[4], strict=True)),
            "product": first(r, 5), "productNum": first(r, 6),
            "gold": first(r, 7), "power": first(r, 8),
            "level": first(r, 9), "unlockType": first(r, 10),
            "unlockParam": first(r, 11), "otherProduct": first(r, 12),
            "otherProductId": first(r, 13)} for k, r in recipes.items()},
        "jewelIds": sorted(jewels),
    }
    (ROOT / "src/x2server/data/bag_client_catalog.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf8")
    print("usable", len(links), "gifts", len(groups), "recipes", len(recipes), "jewels", len(jewels))


if __name__ == "__main__":
    build()
