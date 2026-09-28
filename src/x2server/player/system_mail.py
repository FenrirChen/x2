"""User-approved Revival mail policy; not an official server reward schedule."""
import json

from .mail import ensure_mail_schema
from .task_calendar import task_period

BRILLIANCE = 1237902  # Item E_Currency, EffData 902
WISH_COIN = 1237914  # Item E_Currency, EffData 914
CAUSALITY_CARD = 1202014  # Client Item.Used 720004 -> 100 power; closest existing card to 120.
SENDER = "解神者 Revival"


def insert_system_mail(db, player_id, account_id, kind, now):
    """Call inside the account transaction; UNIQUE source_key owns idempotence."""
    ensure_mail_schema(db)
    if kind == "welcome":
        source_key = f"account_welcome:{account_id}"
        body, rewards = "", {BRILLIANCE: 3600, WISH_COIN: 80}
    elif kind == "daily_login":
        day_start, _ = task_period(1, now)
        source_key = f"daily_login:{account_id}:{day_start}"
        body, rewards = "祝您玩的开心", {BRILLIANCE: 200, WISH_COIN: 10,
                                        CAUSALITY_CARD: 10}
    else:
        raise ValueError("unknown system mail kind")
    return db.execute("""INSERT OR IGNORE INTO player_mail
        (player_id,sender,title,body,created_at,attachments,source_key)
        VALUES (?,?,?,?,?,?,?)""", (player_id, SENDER, "", body, now,
                                json.dumps(rewards, sort_keys=True), source_key)).rowcount == 1
