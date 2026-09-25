"""Inspect the targeted local battle probe without changing player state."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from x2server.messages.battle import BATTLE_SCHEMAS
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S


ITEM = S("ItemDataP", (F(1, "id", K.INT32), F(2, "num", K.INT32),
    F(3, "quality", K.INT32), F(4, "eNum", K.INT32)))
PAIR = S("Pair", (F(1, "key", K.INT32), F(2, "value", K.INT32)))
KILLS = S("FightKillMonster", (F(1, "normal", K.INT32), F(2, "boss", K.INT32),
    F(3, "elite", K.INT32), F(4, "detail", K.MESSAGE, repeated=True)))
CHECKOUT_EXTRA = S("CheckoutExtra", (F(2, "section", K.INT32),
    F(3, "outside_items", K.MESSAGE, repeated=True), F(22, "kills", K.MESSAGE),
    F(30, "npc_events", K.MESSAGE, repeated=True)))
KILL_DATA = S("FightKillData", (F(1, "hero", K.INT32),
    F(2, "unit", K.INT32, repeated=True), F(3, "count", K.INT32, repeated=True)))
KILL_INFO = S("KillInfo", (F(1, "section", K.INT32),
    F(2, "data", K.MESSAGE, repeated=True)))
DROP_INFO = S("DropInfo", (F(1, "section", K.INT32), F(2, "layer", K.INT32),
    F(3, "item", K.INT32), F(4, "quality", K.INT32), F(5, "count", K.INT32)))
LINE = re.compile(r"^(.*?) message=(\d+)/battle-probe request=(\d+) battle probe body=([0-9a-f]*)")


def inspect(message: int, body: bytes) -> dict:
    if message == 887:
        wrapped = BATTLE_SCHEMAS["C2L_CheckoutMainMissionSign"].decode(body)
        raw = wrapped["checkout"]
        values = CHECKOUT_EXTRA.decode(raw)
        values["outside_items"] = [ITEM.decode(x) for x in values.get("outside_items", [])]
        values["kills"] = KILLS.decode(values["kills"]) if "kills" in values else None
        if values["kills"]:
            values["kills"]["detail"] = [PAIR.decode(x) for x in values["kills"].get("detail", [])]
        values["npc_events"] = [PAIR.decode(x) for x in values.get("npc_events", [])]
        values["checkout_bytes"] = len(raw)
        return values
    if message == 316:
        values = KILL_INFO.decode(body)
        values["data"] = [KILL_DATA.decode(x) for x in values.get("data", [])]
        return values
    if message == 323:
        return DROP_INFO.decode(body)
    if message == 126:
        request = BATTLE_SCHEMAS["C2L_FightData"].decode(body)
        return {k: request.get(k) for k in ("missionId", "chapter", "sceneId")}
    return {"body_bytes": len(body)}


def main() -> None:
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        match = LINE.search(line)
        if match is None:
            continue
        stamp, message, request, hex_body = match.groups()
        number = int(message)
        if number not in (126, 316, 323, 887):
            continue
        try:
            result = inspect(number, bytes.fromhex(hex_body))
        except Exception as exc:
            result = {"decode_error": str(exc)}
        print(json.dumps({"time": stamp, "message": number, "request": int(request),
            "data": result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
