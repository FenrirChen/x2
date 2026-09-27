"""Add conservative native-read evidence to the College protocol matrix."""
import csv
from pathlib import Path

path = Path(__file__).resolve().parents[2] / "analysis/white_night_planet/protocol_matrix.csv"
with path.open(encoding="utf-8-sig", newline="") as handle:
    rows = list(csv.DictReader(handle))

extra = ("Evidence", "Consumer RVA", "Required/Optional", "Null-safe", "Phase1 required", "Push dependency")
audit = {
    584: ("washingCountDay; entire response retained in growthData", "ARM64 direct 0x1AF88D4/0x1AF88D8", "0x1AF8850", "response required; individual fields UNKNOWN", "response null-safe; downstream UNKNOWN", "yes", "none proven"),
    591: ("code,recipeIdExp,customeres,productionBars,elements,buffType,buffCount", "ARM64 direct 0x189CD54..0x189D2C8", "0x189CC90", "code=10; four constructed lists required", "null lists unsafe; empty lists loop-safe", "yes, if main-entry refresh enabled", "none proven"),
    623: ("code,unlockExploreRuin", "ARM64 direct 0x1AFE25C..0x1AFE274", "0x1AFE168", "code=10; list optional for storage but no state replacement if null", "null list falls through error logging", "yes", "none proven"),
    250: ("code,rewardData,ruinId,exp", "ARM64 direct 0x1AFD774..0x1AFD784", "0x1AFD670", "UNKNOWN", "UNKNOWN", "no", "ItemUpdate UNKNOWN"),
    599: ("posIndex,rewardData,alchemyType", "ARM64 direct 0x189ED08..0x189EFEC", "0x189EBD8", "UNKNOWN", "UNKNOWN", "no", "ItemUpdate UNKNOWN"),
    603: ("code,recipeId,posIndex; rewardData handoff UNKNOWN", "ARM64 direct 0x189F5A4..0x189F890", "0x189F4C4", "UNKNOWN", "UNKNOWN", "no", "ItemUpdate UNKNOWN"),
    827: ("code,barData; rewardData handoff UNKNOWN", "ARM64 direct 0x18A0EBC..0x18A123C", "0x18A0DCC", "UNKNOWN", "UNKNOWN", "no", "ItemUpdate UNKNOWN"),
    372: ("code,rewardData", "ARM64 direct 0x1DB726C/0x1DB7334", "0x1DB7190", "UNKNOWN", "UNKNOWN", "no", "ItemUpdate UNKNOWN"),
}
for row in rows:
    values = audit.get(int(row["L2C ID"]))
    if values:
        row["Response fields used"] = values[0]
        row.update(dict(zip(extra, values[1:])))
    else:
        row["Response fields used"] = "UNKNOWN (declared fields in client_code_map.md)"
        row.update(dict(zip(extra, ("declaration only", row["Handler"].split(" @ ")[-1] if " @ " in row["Handler"] else "UNKNOWN", "UNKNOWN", "UNKNOWN", "no", "UNKNOWN"))))

with path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=list(rows[0]) + [field for field in extra if field not in rows[0]])
    writer.writeheader()
    writer.writerows(rows)
