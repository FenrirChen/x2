"""Export battle-entry metadata from the existing indexed client tables.

This uses the already selected table versions; it does not scan APK bundles.
Runtime policies are deliberately kept outside this static catalog.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "analysis" / "progression"))
from probe import read_tables  # noqa: E402


def enum_value(value, default=0):
    return value.get("value", default) if isinstance(value, dict) else value if isinstance(value, int) else default


def main():
    tables, sources, missing = read_tables(["SectionTable", "DailyDungeon"])
    if missing:
        raise RuntimeError(f"indexed battle tables missing: {missing}")
    fields = ("SectionID", "ChapterID", "NextSectionID", "Maps", "ManualValue", "Open",
              "OpenType", "OpenParam", "HeroLimit", "AssistType", "AssistParam",
              "FirVReward", "VReward", "MopReward", "ContinueFightID", "ContinueFightConsume")
    sections = []
    for row in tables["SectionTable"]:
        record = {key: row[key] for key in fields if key in row}
        record["Type"] = enum_value(row.get("Type"))
        record["TypeName"] = row.get("Type", {}).get("enum", "E_guanqia") if isinstance(row.get("Type"), dict) else "E_guanqia"
        sections.append(record)
    dungeons = []
    for row in tables["DailyDungeon"]:
        dungeons.append({key: row[key] for key in ("ID", "GameplayType", "GameplayParam01", "SectionID",
                         "OpenTime", "Limit", "MonthCardLimit") if key in row})
    output = ROOT / "src" / "x2server" / "data" / "battle_entry_catalog.json"
    output.write_text(json.dumps({"provenance": sources, "sections": sections, "daily_dungeons": dungeons},
                                 ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(sections)} sections, {len(dungeons)} daily dungeons -> {output}")


if __name__ == "__main__":
    main()
