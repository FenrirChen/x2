"""Export a small deterministic test set from already indexed Equib tables."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis/progression"))
from probe import read_tables  # noqa: E402


def main():
    tables, sources, missing = read_tables(["EquibBase", "EquibAttribBD"])
    if missing:
        raise RuntimeError(missing)
    bases = [r for r in tables["EquibBase"] if r["EquibSuit"] in range(400, 407)]
    presets = {r["AttrbdID"]: r for r in tables["EquibAttribBD"]}
    rows = []
    for base in sorted(bases, key=lambda r: r["EquibId"]):
        part = base["EquibPart"]
        quality = 5 if base["EquibSuit"] == 406 else 6
        preset = presets[10_000_000 + quality * 1_000_000 + 100 + part]
        main_type, main_value = preset["MainAttr"][:2]
        if main_type not in base["MainAttrType"]:
            raise ValueError(f"preset main attribute invalid for {base['EquibId']}")
        param = {"at1": main_type, "av1": main_value}
        for index, (kind, value) in enumerate(zip(preset["MinorAttrType"], preset["MinorAttrValue"]), 2):
            if kind and kind not in base["MinorAttrType"]:
                raise ValueError(f"preset minor attribute invalid for {base['EquibId']}")
            param[f"at{index}"] = kind
            param[f"av{index}"] = value
        rows.append({"type_id": base["EquibId"], "part": part, "suit": base["EquibSuit"],
                     "star": quality, "preset_id": preset["AttrbdID"], "param": param,
                     "marker": "TEST_COMPAT_INSTANCE"})
    if len(rows) != 42:
        raise ValueError(f"expected 42 representative instances, found {len(rows)}")
    out = ROOT / "analysis/progression/equipment_seed_catalog.json"
    out.write_text(json.dumps({"sources": sources, "rows": rows,
        "policy": "TEST_COMPAT_INSTANCE; static attribute preset reused deterministically, not an official drop roll"},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(rows)} representative types to {out}")


if __name__ == "__main__":
    main()
