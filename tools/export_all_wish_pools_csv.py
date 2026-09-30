"""Export every recovered wish pool and its weighted reward entries."""
import argparse
import csv
import json
from pathlib import Path


CATALOG = Path(__file__).resolve().parents[1] / "src/x2server/data/wish_catalog.json"
FIELDS = ("pool_id", "pool_type", "draw_count_id", "ticket_item_id", "one_ticket",
          "one_crystal", "one_power_of_light", "three_star_security", "hero_security",
          "limit_num", "limit_items", "reward_group", "item_id", "quantity", "weight")


def export(target: Path) -> tuple[int, int]:
    pools = json.loads(CATALOG.read_text(encoding="utf-8"))
    target.parent.mkdir(parents=True, exist_ok=True)
    entries = 0
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        for pool_id, pool in sorted(pools.items(), key=lambda entry: int(entry[0])):
            common = {"pool_id": pool_id, "pool_type": pool["type"],
                      "draw_count_id": pool["draw_count_id"],
                      "ticket_item_id": pool["ticket_item_id"],
                      "one_ticket": pool["one_ticket"], "one_crystal": pool["one_crystal"],
                      "one_power_of_light": pool.get("one_power_of_light", 0),
                      "three_star_security": pool["three_star_security"],
                      "hero_security": pool["hero_security"], "limit_num": pool["limit_num"],
                      "limit_items": ";".join(map(str, pool["limit_items"]))}
            for group, rewards in pool["groups"].items():
                for reward in rewards:
                    writer.writerow({**common, "reward_group": group, **reward})
                    entries += 1
    return len(pools), entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    pool_count, entry_count = export(args.target)
    print(f"{args.target}: {pool_count} pools, {entry_count} reward entries")
