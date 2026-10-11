"""Generate the per-table save-boundary inventory from the live database schema.

Read-only against runtime/phase14/player.sqlite3. Emits a markdown table plus a
machine-readable JSON consumed by the save manager implementation, so the
audit and the code cannot drift apart.
"""
import json
import re
import sqlite3
import sys
from pathlib import Path

DB = Path(sys.argv[1] if len(sys.argv) > 1 else "runtime/phase14/player.sqlite3")
OUT_JSON = Path("tools/savemanager/save_boundary.json")

# Ownership derivation for tables WITHOUT a player_id column.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from x2server.player.save_manager import JOIN_OWNERS
JOINED_OWNERS = JOIN_OWNERS

EXCLUDED_TABLES = {
    "system_mail_issues": "服务器一次性邮件发放历史，禁止随存档迁移或回滚以防重复领取。",
    "world_boss_days": "全服 BOSS 日历，不随单个玩家存档覆盖。",
    "accounts": "账号认证身份（username/password_hash/status/created_at/last_login_at）。存档代表游戏状态，不代表登录身份；导入必须保留目标账号的凭据。",
    "repair_history": "服务器运维修复记录（repair_key/applied_at/backup_path），不属于任何玩家游戏状态。",
}
EXCLUDED_PLAYER_COLUMNS = {
    "id": "player 主键 = 认证身份绑定键，导入保持目标 player 行不变",
    "account": "与 accounts.username 绑定的登录身份，导入不得覆盖",
    "created_at": "账号建档时间，属于身份活动数据",
    "login_count": "登录次数计数，属于账号活动数据",
    "revision": "乐观并发控制技术字段，导入后由服务器重置",
}

JSON_TEXT_COLUMNS = {
    "players.snapshot", "college_state.state_json", "economy_grants.rewards",
    "fight_drop_observations.decoded", "fight_drop_observations.context",
    "fight_drop_claims.decoded", "battle_entries.team_json",
    "player_mail.attachments", "reward_settlement_audit.sources",
    "reward_settlement_audit.blocked", "chapter_dp_migrations.legacy_floors",
}
BLOB_COLUMNS = set()
AUTOINC_TABLES = {"equipment_instances": "id", "player_mail": "id",
                  "fight_drop_observations": "id", "accounts": "account_id"}
# battle_receipts/battle_checkout_wire/economy_runs keyed by client uuid text; no remap.


def parse_columns(sql: str):
    body = sql[sql.index("(") + 1:sql.rindex(")")]
    parts, depth, cur = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    cols = []
    for part in parts:
        head = part.split()[0]
        if head.upper() in ("PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "CONSTRAINT"):
            continue
        cols.append((head, part))
    return cols


def pk_from(sql: str, cols):
    m = re.search(r"PRIMARY\s+KEY\s*\(([^)]*)\)", sql, re.I)
    if m:
        return [c.strip().strip('"') for c in m.group(1).split(",")]
    for name, part in cols:
        if re.search(r"\bPRIMARY\s+KEY\b", part, re.I) and "AUTOINCREMENT" not in part.upper():
            pass
    inline = [name for name, part in cols if re.search(r"\bPRIMARY\s+KEY\b", part, re.I)]
    return inline


db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row
tables = [r[0] for r in db.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
rows_out = []
for t in tables:
    sql = db.execute("SELECT sql FROM sqlite_master WHERE name=?", (t,)).fetchone()[0]
    cols = parse_columns(sql)
    pk = pk_from(sql, cols)
    colnames = [c for c, _ in cols]
    owner = "player_id" if "player_id" in colnames else None
    blobs = [c for c, _ in cols
             if re.search(r"\bBLOB\b", dict(cols)[c], re.I)]
    BLOB_COLUMNS.update(f"{t}.{c}" for c in blobs)
    jsons = [c for c in colnames if f"{t}.{c}" in JSON_TEXT_COLUMNS]
    included = t not in EXCLUDED_TABLES and t != "players"
    rows_out.append({
        "table": t, "columns": colnames, "primary_key": pk,
        "owner_column": owner,
        "owner_join": JOINED_OWNERS.get(t),
        "included": included or t == "players",
        "blob_columns": blobs, "json_columns": jsons,
        "autoincrement": AUTOINC_TABLES.get(t),
    })

OUT_JSON.write_text(json.dumps({
    "database": str(DB.resolve()),
    "user_version": db.execute("PRAGMA user_version").fetchone()[0],
    "excluded_tables": EXCLUDED_TABLES,
    "excluded_player_columns": EXCLUDED_PLAYER_COLUMNS,
    "tables": rows_out,
}, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"{len(rows_out)} tables catalogued -> {OUT_JSON}")
inc = sum(1 for r in rows_out if r["included"])
print(f"included (fully or snapshot-special): {inc}, excluded: {len(rows_out) - inc}")
