"""One-time compensation for the pre-2026-10-31 power price ladder.

Old daily ordinals reconstruct the OLD_LADDER minus 60 per purchase. This is
legacy evidence, not an original per-purchase price receipt. New purchases use
power-buy-v2 and a snapshot price_version, so they are never reconstructed as
old overcharges. Aggregate below zero is not charged back.

The first service initialization freezes existing account/player eligibility
in global server_settings. Global system_mail_issues records settlement even
when zero, survives save replacement and prevents reminting after mail removal.
Both the mail and marker are in the caller's transaction. Missing old evidence
is not invented. No database-wide history scan runs during startup.
"""
import json
import logging
import sqlite3

from .mail import ensure_mail_schema
from .system_mail import remember_once_mail_history

LOGGER = logging.getLogger("x2.power_refund")

# 修复前的 20 档阶梯, 只用于算差额。
OLD_LADDER = (20, 20, 40, 60, 80, 100, 120, 150, 180, 220,
              260, 300, 350, 400, 460, 520, 600, 700, 800, 1000)
# 客户端 ServerData..ctor 的出厂价, 也是现在的成交价。
FAIR_PRICE = 60
BRILLIANCE = 1237902  # 光辉
SENDER = "解神者 Revival"
TITLE = "购买因果差价返还"
BODY = ("服务器在修复前按旧阶梯扣除光辉，而购买页每档显示 60 光辉。"
        "本封邮件返还您此前被多扣的光辉，共 {} 光辉。"
        "问题已于 2026-10-31 修复，今后每次购买因果固定 60 光辉。")
SOURCE = "power_refund_20261031:%s"
KIND = 'power_refund_20261031'
BASELINE = KIND + ':eligibility'


def initialize(db):
    """Freeze server-owned account eligibility before new-price traffic starts."""
    db.execute('CREATE TABLE IF NOT EXISTS server_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL)')
    if db.execute('SELECT 1 FROM server_settings WHERE key=?',(BASELINE,)).fetchone():
        return
    limits={name:db.execute(f'SELECT COALESCE(MAX({column}),0) FROM {name}').fetchone()[0]
            for name,column in (('players','id'),('accounts','account_id'))}
    db.execute('INSERT OR IGNORE INTO server_settings VALUES (?,?)',(BASELINE,json.dumps(limits)))


def eligible(db, player_id):
    initialize(db)
    limits=json.loads(db.execute('SELECT value FROM server_settings WHERE key=?',(BASELINE,)).fetchone()[0])
    account=db.execute('SELECT account_id FROM accounts WHERE player_id=?',(player_id,)).fetchone()
    return (account[0]<=limits['accounts'] if account else player_id<=limits['players'])


def purchases_by_day(db, player_id: int) -> dict[int, int]:
    """当日第几次购买 (键里的日 -> 该日最大的购买序号)。

    ``economy_events`` 可能还没建, 所以缺表按「没有任何记录」处理, 让 snapshot 的
    当日计数继续兜底。
    """
    days: dict[int, int] = {}
    try:
        rows = db.execute(
            "SELECT event_key FROM economy_events WHERE player_id=? AND "
            "(event_key LIKE '%power_buy:%' OR event_key LIKE '%power-buy:%')",
            (player_id,)).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" not in str(exc):
            raise
        LOGGER.info("power purchase ledger unavailable player=%s (%s)", player_id, exc)
        return days
    for row in rows:
        tokens = str(row[0]).split(":")
        for index, token in enumerate(tokens[:-2]):
            if token in ("power_buy", "power-buy"):
                try:
                    day, ordinal = int(tokens[index + 1]), int(tokens[index + 2])
                except (TypeError, ValueError):
                    break
                if day >= 0 and 0 < ordinal <= 2**31-1:
                    days[day] = max(days.get(day, 0), ordinal)
                break
    return days


def overcharge_for(purchases: int) -> int:
    """当日买了 ``purchases`` 次, 旧阶梯比平价 60 多收了多少光辉。"""
    purchases = max(int(purchases), 0)
    head = min(purchases, len(OLD_LADDER))
    return sum(p - FAIR_PRICE for p in OLD_LADDER[:head]) + max(0,purchases-head)*(OLD_LADDER[-1]-FAIR_PRICE)


def refund_amount(db, player_id: int, snapshot: dict) -> tuple[int, dict[int, int]]:
    """(应返还总数, 逐日购买次数)。纯计算, 不写库。"""
    days = purchases_by_day(db, player_id)
    state = snapshot.get("power_buy") or {}
    if state and state.get("price_version",1) == 1:
        # snapshot 的 day 与键里的 day 同一口径(task_period(1, now) 的日起点),
        # 所以同一天取较大值; 只赢在「账本缺行」这一种情况上。
        try:
            day, count = int(state.get("day", -1)), int(state.get("count", 0))
        except (TypeError, ValueError):
            day, count = -1, 0
        if day >= 0 and 0 < count <= 2**31-1:
            days[day] = max(days.get(day, 0), count)
    return sum(overcharge_for(count) for count in days.values()), days


def settle(db, player_id: int, snapshot: dict, now: int) -> int:
    """给这个角色发一封差价返还邮件, 返回这次实际入账的光辉(0 = 无需/已发过)。

    调用方负责事务; 邮件走 ``player_mail`` 的 source_key 唯一索引, 所以登录、重连、
    甚至运维手动重跑都只会成功一次。
    """
    ensure_mail_schema(db)
    remember_once_mail_history(db, player_id)
    if db.execute('SELECT 1 FROM system_mail_issues WHERE player_id=? AND kind=?',(player_id,KIND)).fetchone():
        return 0
    amount,days=refund_amount(db,player_id,snapshot) if eligible(db,player_id) else (0,{})
    if amount > 2**31-1:
        raise ValueError('power refund amount exceeds mail integer limit')
    db.execute('INSERT INTO system_mail_issues VALUES (?,?)',(player_id,KIND))
    if amount <= 0:
        return 0
    inserted = db.execute(
        """INSERT OR IGNORE INTO player_mail
        (player_id,sender,title,body,created_at,attachments,source_key)
        VALUES (?,?,?,?,?,?,?)""",
        (player_id, SENDER, TITLE, BODY.format(amount), int(now),
         json.dumps({str(BRILLIANCE): amount}), SOURCE % player_id)).rowcount
    if not inserted:
        return 0
    LOGGER.info("power refund minted player=%s amount=%s days=%s",
                player_id, amount, dict(sorted(days.items())))
    return amount
