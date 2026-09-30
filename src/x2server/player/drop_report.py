"""Pure 264 observation. Records statements; never constructs rewards/budgets."""
import hashlib
import json
import time
from x2server.messages.battle import DROP_REPORT_ITEM, DROP_REPORT_NPC, DROP_REPORT_SPAN
from x2server.protocol.errors import ProtobufDecodeError


def json_values(value):
    if isinstance(value, bytes):
        return {"hex": value.hex()}
    if isinstance(value, dict):
        return {k: json_values(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_values(v) for v in value]
    return value


class FightDropRecorder:
    def __init__(self, store):
        self.db = store.db
        self.db.execute("""CREATE TABLE IF NOT EXISTS fight_drop_observations (
            id INTEGER PRIMARY KEY, player_id INTEGER, uuid TEXT, session_id TEXT, request_id INTEGER,
            digest TEXT, recorded_at INTEGER, body BLOB, decoded TEXT, context TEXT,
            UNIQUE(player_id,uuid,digest))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS fight_drop_items (
            report_id INTEGER, position INTEGER, item_id INTEGER, value INTEGER, variant INTEGER,
            in_relic_list INTEGER, PRIMARY KEY(report_id,position))""")
        self.db.execute("""CREATE TABLE IF NOT EXISTS fight_drop_claims (
            report_id INTEGER, field TEXT, position INTEGER, decoded TEXT,
            PRIMARY KEY(report_id,field,position))""")

    def record(self, player, session, request_id, run, body, values, context):
        cursor = self.db.execute("INSERT OR IGNORE INTO fight_drop_observations VALUES (NULL,?,?,?,?,?,?,?,?,?)",
            (player, run, session, request_id, hashlib.sha256(body).hexdigest(), int(time.time()), body,
             json.dumps(json_values(values), sort_keys=True), json.dumps(context, sort_keys=True)))
        if not cursor.rowcount:
            return False
        report = cursor.lastrowid
        for index, raw in enumerate(values.get("dropItem", [])):
            item = DROP_REPORT_ITEM.decode(raw)
            self.db.execute("INSERT INTO fight_drop_items VALUES (?,?,?,?,?,?)", (report, index,
                item.get("itemId", 0), item.get("value", 0), item.get("variant", 0),
                int(item.get("itemId") in values.get("relicList", []))))
        for field in ("npcData", "currency", "heros", "killMonster", "antiCheat"):
            entries = values.get(field, [])
            if isinstance(entries, bytes):
                entries = [entries]
            for index, raw in enumerate(entries):
                schema = DROP_REPORT_NPC if field == "npcData" else DROP_REPORT_SPAN
                try:
                    decoded = schema.decode(raw) if field != "antiCheat" else {"hex": raw.hex()}
                except (ProtobufDecodeError, ValueError, TypeError):
                    decoded = {"hex": raw.hex(), "decodeError": True}
                self.db.execute("INSERT INTO fight_drop_claims VALUES (?,?,?,?)",
                    (report, field, index, json.dumps(decoded, sort_keys=True)))
        return True
