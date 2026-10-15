"""User-approved Revival mail policy; not an official server reward schedule."""
import json
import logging
import os

from .season_schedule import current_season

from .mail import ensure_mail_schema
from .task_calendar import task_period

WELFARE_POLL_SECONDS = 300.0

BRILLIANCE = 1237902  # Item E_Currency, EffData 902
WISH_COIN = 1237914  # Item E_Currency, EffData 914
BIO_POWER = 1237922  # 生物电源
PURE_CRYSTAL = 1237925
CAUSALITY_CARD = 1202014  # Client Item.Used 720004 -> 100 power; closest existing card to 120.
HERO_CHOICE_BOX = 1290005
ULTIMATE_CAUSALITY_CARD = 1202014
SENDER = "解神者 Revival"

ONCE_MAIL_PREFIXES = {
    'welcome': ('welcome_mail:', 'account_welcome:'),
    'hero_choice': ('hero_choice_1290005:',),
    'ultimate_causality': ('ultimate_causality_50:',),
    'revival_supply': ('revival_supply_200_7200_140:',),
    'causality_oct13': ('causality_gift_20261013_50:',),
}


def remember_once_mail_history(db, player_id):
    """Server-owned issuance history survives save replacement and owner changes."""
    db.execute('''CREATE TABLE IF NOT EXISTS system_mail_issues (
        player_id INTEGER NOT NULL, kind TEXT NOT NULL,
        PRIMARY KEY(player_id,kind))''')
    for row in db.execute('SELECT source_key FROM player_mail WHERE player_id=? AND source_key IS NOT NULL', (player_id,)):
        for kind, prefixes in ONCE_MAIL_PREFIXES.items():
            if row[0].startswith(prefixes):
                db.execute('INSERT OR IGNORE INTO system_mail_issues VALUES (?,?)', (player_id, kind))


def insert_system_mail(db, player_id, account_id, kind, now):
    """Call inside the account transaction; UNIQUE source_key owns idempotence."""
    ensure_mail_schema(db)
    remember_once_mail_history(db, player_id)
    if kind in ONCE_MAIL_PREFIXES and db.execute(
            'SELECT 1 FROM system_mail_issues WHERE player_id=? AND kind=?',
            (player_id, kind)).fetchone():
        return False
    title = ""
    if kind == "welcome":
        source_key = f"welcome_mail:{account_id}"
        body, rewards = "", {BRILLIANCE: 3600, WISH_COIN: 80}
    elif kind == "daily_login":
        day_start, _ = task_period(1, now)
        source_key = f"daily_login:{account_id}:{day_start}"
        body, rewards = "祝您玩的开心", {BRILLIANCE: 200, WISH_COIN: 10,
                                        CAUSALITY_CARD: 10, PURE_CRYSTAL: 10, BIO_POWER: 700}
    elif kind == "daily_season_ticket":
        season = current_season(now)
        if (os.getenv('X2_ORIGIN_SEASON_ENABLED','0') != '1' or not season
                or not season['implemented']):
            return False
        day_start, _ = task_period(1, now)
        source_key = f"daily_season_ticket:{player_id}:{day_start}"
        title = "每日赛季挑战券"
        body = f"为您送上10张{season['name']}挑战券。"
        rewards = {season['ticket']: 10}
    elif kind == "hero_choice":
        # Stable per player even when a legacy save is later bound to an account.
        source_key = f"hero_choice_1290005:{player_id}"
        title = "自选3★神格赠礼"
        body, rewards = "为您送上1个自选3★神格箱。", {HERO_CHOICE_BOX: 1}
    elif kind == "ultimate_causality":
        source_key = f"ultimate_causality_50:{player_id}"
        title = "终极因果卡赠礼"
        body, rewards = "为您送上50张终极因果卡，祝您旅途愉快。", {ULTIMATE_CAUSALITY_CARD: 50}
    elif kind == "causality_oct13":
        source_key = f"causality_gift_20261013_50:{player_id}"
        title = "终极因果卡补给"
        body, rewards = "为您送上50张终极因果卡。每位玩家仅可领取一次。", {ULTIMATE_CAUSALITY_CARD: 50}
    elif kind == "revival_supply":
        source_key = f"revival_supply_200_7200_140:{player_id}"
        title = "旅途补给赠礼"
        body, rewards = "为您送上200张终极因果卡、7200光辉和140枚许愿币。", {
            ULTIMATE_CAUSALITY_CARD: 200, BRILLIANCE: 7200, WISH_COIN: 140}
    else:
        raise ValueError("unknown system mail kind")
    if kind == "welcome":
        if db.execute("SELECT 1 FROM player_mail WHERE player_id=? AND source_key IN (?,?) LIMIT 1",
                      (player_id, source_key, f"account_welcome:{account_id}")).fetchone():
            return False
    created = db.execute("""INSERT OR IGNORE INTO player_mail
        (player_id,sender,title,body,created_at,attachments,source_key)
        VALUES (?,?,?,?,?,?,?)""", (player_id, SENDER, title, body, now,
                                json.dumps(rewards, sort_keys=True), source_key)).rowcount == 1
    if created and kind in ONCE_MAIL_PREFIXES:
        db.execute('INSERT OR IGNORE INTO system_mail_issues VALUES (?,?)', (player_id, kind))
    return created


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


def deliver_ultimate_causality(store, now):
    """One gift per player, including offline and unbound legacy saves."""
    return deliver_player_gift(store, now, "ultimate_causality")


def deliver_revival_supply(store, now):
    """Independent one-time supply, retaining its key after claim or deletion."""
    return deliver_player_gift(store, now, "revival_supply")


def deliver_player_gift(store, now, kind):
    minted, failed = 0, []
    for player_id, account_id in store.db.execute('''SELECT p.id,a.account_id FROM players p
            LEFT JOIN accounts a ON a.player_id=p.id''').fetchall():
        try:
            with store.db:
                minted += insert_system_mail(store.db, player_id, account_id or player_id,
                                              kind, int(now))
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
                minted += insert_system_mail(store.db, player_id, account_id or player_id,
                                              "daily_season_ticket", int(now))
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
                    logging.getLogger("x2.system_mail").exception("daily rollover callback failed")
            minted, failed = deliver_daily_welfare(store, now)
            logging.getLogger("x2.system_mail").info("daily welfare sweep minted=%s failed=%s", minted, failed)
            if not failed:
                completed_day = day_start
        await asyncio.sleep(poll)
