"""Freeze contributor B's shop offers as clearly labeled compatibility data."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT.parent / "other/9.26 修复包/9.26 修复包/server/src/x2server/data/shop_goods.json"
OUTPUT = ROOT / "src/x2server/data/shop_compat_catalog.json"


if __name__ == "__main__":
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    shops = {id_: rows["goods"] for id_, rows in source["shops"].items() if id_ != "809"}
    assert sum(map(len, shops.values())) == 130
    OUTPUT.write_text(json.dumps({"status": "REVIVAL_COMPATIBILITY / USER_DECISION",
        "source": str(SOURCE), "shops": shops}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
