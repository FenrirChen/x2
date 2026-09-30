"""Select banner metadata/artwork only; never import gift rotation or rewards."""
import argparse
import json
import shutil
from pathlib import Path


def build(package, output):
    selected = json.loads((output / "selected_gift_packages.json").read_text(encoding="utf-8"))
    ids = {r["GiftPackageID"] for r in selected["packages"]}
    source = package / "server/src/x2server/data"
    catalog = json.loads((source / "gift_package_shop.json").read_text(encoding="utf-8"))
    icons = json.loads((source / "gift_icons.json").read_text(encoding="utf-8"))["packages"]
    rows = catalog["packages"]
    if isinstance(rows, dict):
        rows = rows.values()
    result = {}
    fallback = next(v for v in icons.values() if (source / v["file"]).is_file())
    for row in rows:
        if row["id"] not in ids or not row.get("jumpId"):
            continue
        icon = icons.get(str(row["id"]), fallback)
        destination = output / "gifticon" / f"{row['id']}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / icon["file"], destination)
        result[str(row["id"])] = {"name": row["name"], "jumpId": row["jumpId"],
            "image": f"gifticon/{row['id']}.png", "imageRule": icon.get("rule", "exact") if str(row["id"]) in icons else "fallback",
            "donor": icon.get("donor", "")}
    (output / "recommendations.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[2] / "src/x2server/data")
    args = parser.parse_args()
    build(args.package, args.output)
