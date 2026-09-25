"""Exercise every extracted Section in an in-memory player database."""
import asyncio
import json
import sys
from pathlib import Path

from tests.unit.test_battle import packet, request
from x2server.messages.battle import CHECKOUT
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore


def main():
    expert = "--expert" in sys.argv
    store = PlayerStore(Path(":memory:"))
    player = store.login("section-probe", 1, 0)
    snapshot = dict(player["snapshot"], level=100, mobility={"power": 1_000_000},
                    heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}])
    store.save_snapshot(1, snapshot, player["revision"])
    economy = EconomyService(store)
    battle = BattleService(store, economy)
    context = DispatchContext("probe", "local", SessionState("probe", "section-probe", player_id=1))
    # This probe tests the transport/settlement mechanics after known unlocks.
    with store.db:
        for row in battle.catalog.sections.values():
            if row.get("OpenType", {}).get("value") == 2 and row.get("OpenParam"):
                store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)",
                                 (1, row["OpenParam"], "probe-prerequisite"))
        for dungeon in battle.catalog.daily_dungeons.values():
            for section in dungeon["SectionID"]:
                store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)",
                                 (1, section, "probe-daily-prerequisite"))
    counts = {}
    failed = []
    for index, row in enumerate(battle.catalog.sections.values(), 1):
        section, chapter = row["SectionID"], row["ChapterID"]
        values = request()
        values.update(missionId=section, chapter=chapter, sceneId=row["Maps"][0],
                      expertMode=expert)
        try:
            entry = asyncio.run(battle.enter(context, packet(values, 10000 + index)))
            if entry.values["result"] != 10:
                failed.append([section, row["Type"], "entry", entry.values])
                continue
            drop = asyncio.run(battle.drop_data(context, packet({"missionId": section,
                "chapterId": chapter, "expertMode": expert}, name="C2L_FightDropData")))
            if drop.values["result"] != 10:
                failed.append([section, row["Type"], "drop", drop.values])
                continue
            done = packet({"checkout": CHECKOUT.encode({"chapterId": chapter,
                "sectionId": section, "success": True, "expertMode": expert,
                "fightTime": 120})},
                name="C2L_CheckoutMainMissionSign")
            result = asyncio.run(battle.checkout(context, done))
            if result.values["result"] != 10:
                failed.append([section, row["Type"], "checkout", result.values])
                continue
            counts[row["Type"]] = counts.get(row["Type"], 0) + 1
        except Exception as exc:
            failed.append([section, row["Type"], "exception", repr(exc)])
        if index % 500 == 0:
            print("progress", index, "failures", len(failed), flush=True)
    print(json.dumps({"total": len(battle.catalog.sections), "expert": expert,
                      "settled_by_type": counts,
                      "failures": failed[:50], "failure_count": len(failed)}, ensure_ascii=False))
    store.close()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
