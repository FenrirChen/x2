"""User-approved Revival mail policy; not an official server reward schedule."""
import json

from .mail import ensure_mail_schema
from .task_calendar import task_period

WELFARE_POLL_SECONDS = 300.0

BRILLIANCE = 1237902  # Item E_Currency, EffData 902
WISH_COIN = 1237914  # Item E_Currency, EffData 914
PURE_CRYSTAL = 1237925
CAUSALITY_CARD = 1202014  # Client Item.Used 720004 -> 100 power; closest existing card to 120.
HERO_CHOICE_BOX = 1290005
SENDER = "解神者 Revival"


def insert_system_mail(db, player_id, account_id, kind, now):
    """Call inside the account transaction; UNIQUE source_key owns idempotence."""
    ensure_mail_schema(db)
    title = ""
    if kind == "welcome":
        source_key = f"welcome_mail:{account_id}"
        body, rewards = "", {BRILLIANCE: 3600, WISH_COIN: 80}
    elif kind == "daily_login":
        day_start, _ = task_period(1, now)
        source_key = f"daily_login:{account_id}:{day_start}"
        body, rewards = "祝您玩的开心", {BRILLIANCE: 200, WISH_COIN: 10,
                                        CAUSALITY_CARD: 10, PURE_CRYSTAL: 10}
    elif kind == "hero_choice":
        # Stable per player even when a legacy save is later bound to an account.
        source_key = f"hero_choice_1290005:{player_id}"
        title = "自选3★神格赠礼"
        body, rewards = "为您送上1个自选3★神格箱。", {HERO_CHOICE_BOX: 1}
    else:
        raise ValueError("unknown system mail kind")
    if kind == "welcome":
        if db.execute("SELECT 1 FROM player_mail WHERE player_id=? AND source_key IN (?,?) LIMIT 1",
                      (player_id, source_key, f"account_welcome:{account_id}")).fetchone():
            return False
    return db.execute("""INSERT OR IGNORE INTO player_mail
        (player_id,sender,title,body,created_at,attachments,source_key)
        VALUES (?,?,?,?,?,?,?)""", (player_id, SENDER, title, body, now,
                                json.dumps(rewards, sort_keys=True), source_key)).rowcount == 1


def eligible_accounts(db):
    """Return active player/account pairs, including offline players."""
    return db.execute("""SELECT p.id, a.account_id FROM players p
        LEFT JOIN accounts a ON a.player_id=p.id
        WHERE a.status IS NULL OR a.status='active'""").fetchall()


def deliver_hero_choice(store, now):
    """Backfill offline/legacy players; deleted or claimed mail keeps its key."""
    minted, failed = 0, []
    for player_id, account_id in store.db.execute("""SELECT p.id, a.account_id FROM players p
            LEFT JOIN accounts a ON a.player_id=p.id""").fetchall():
        try:
            with store.db:
                minted += insert_system_mail(store.db, player_id, account_id or player_id,
                                              "hero_choice", int(now))
        except Exception as exc:
            failed.append((player_id, str(exc)))
    return minted, failed


def deliver_daily_welfare(store, now):
    """Insert today's welfare mail for every eligible account idempotently."""
    minted, failed = 0, []
    for player_id, account_id in eligible_accounts(store.db):
        try:
            with store.db:
                if insert_system_mail(store.db, player_id, account_id or player_id,
                                       "daily_login", int(now)):
                    minted += 1
        except Exception as exc:  # one broken row must not stop the sweep
            failed.append((player_id, str(exc)))
    return minted, failed


async def daily_welfare_watch(store, clock, poll=WELFARE_POLL_SECONDS, on_new_day=None):
    """Sweep once at each Beijing day boundary, retrying failed rows.

    ``on_new_day(day_start)`` runs after a fresh boundary is detected (before the
    completed-day marker is set), so callers can settle daily state - e.g. the
    month-card allowance - for players that stayed online across midnight.
    """
    import asyncio
    completed_day = None
    while True:
        now = int(clock())
        day_start, _ = task_period(1, now)
        if completed_day != day_start:
            if on_new_day is not None:
                try:
                    await on_new_day(day_start)
                except Exception:  # rollover callbacks must not kill the sweep
                    import logging
                    logging.getLogger("x2.system_mail").exception("daily rollover callback failed")
            _, failed = deliver_daily_welfare(store, now)
            if not failed:
                completed_day = day_start
        await asyncio.sleep(poll)
