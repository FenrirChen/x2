"""购买因果 (134/137) 超收光辉的一次性返还 —— 2026-10-31 修复的售后部分。

问题本身
--------
此前服务端按 20 档阶梯 20/20/40/60/80/…/220/…/1000 扣光辉, 而客户端「购买因果」
页对**每一档**都显示 60:

* 价格来自客户端自己: ``PowerModule_GetPrice`` (0x015C4F3C) 拿
  ``MainModule_ServerData.PowerPrice`` 按 ``PowerTimesInterval`` 选档;
* ``ServerData..ctor`` (0x13CD7D0) 的出厂值是 ``PowerPrice = [60,60,60,60,60]``、
  ``PowerTimesInterval = {1,2,4,6,10}``, 即每档都是 60;
* 服务端没在 ``L2C_ServerTableConfig`` 里下发 ``PowerPrice`` / ``PowerTimesInterval``,
  客户端便一直用上面这组出厂值显示 60;
* 于是第 1..4 次实际扣 20/20/40/60, 从第 5 次起变贵, 第 10 次 220、第 20 次 1000
  —— 就是玩家报的「写着 60 实际扣得更多, 买超过 10 次才明显, 一次扣了一千多」。

现在 economy.POWER_BUY_PRICES 已改成平价 60, 并由 login.server_config 下发同一组
表, 显示价 == 扣费。本模块负责把**已经多扣的那部分**退还给玩家。

退款金额怎么算出来的
--------------------
服务端没有写价格台账, 但每次购买都会往 ``economy_events`` 写一条去重键::

    1:<日周期起点>:power-buy:<日>:<第几次>

「第几次」就是当日第几次购买, 单调递增, 所以把**当日最大的那个序号**拿旧阶梯回放
一遍, 就精确得到该日实扣总额, 减去平价 60 × 次数 就是该日多扣的光辉。
snapshot 里仍活着的 ``power_buy`` 计数再兜一层底 —— 玩家当时若没有生效中的日常/
周常周期, ``_event`` 不会写行, 那就只剩这个计数; 两处都按同一天取较大值, 不会重复计算。

两处证据都没有的日子无法证明, 不回填。那种情况可以拿服务端日志
``power purchase player=… tier=… price=…`` 来手工补。

幂等
----
返还走一封系统邮件, ``player_mail.source_key = power_refund_20261031:<player_id>``,
由 ``player_mail_source`` 唯一索引保证每个角色一辈子只发一封(领取或删除后也不会再发)。
本仓库的 player_mail 没有 expire_at 列, 所以这里只写公共列 (其余走表默认值)。
"""
import json
import logging

from .mail import ensure_mail_schema

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
    except Exception as exc:  # noqa: BLE001 - 缺表/旧库都不该拦住登录
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
                days[day] = max(days.get(day, 0), ordinal)
                break
    return days


def overcharge_for(purchases: int) -> int:
    """当日买了 ``purchases`` 次, 旧阶梯比平价 60 多收了多少光辉。"""
    purchases = max(int(purchases), 0)
    return sum(OLD_LADDER[min(index, len(OLD_LADDER) - 1)] - FAIR_PRICE
               for index in range(purchases))


def refund_amount(db, player_id: int, snapshot: dict) -> tuple[int, dict[int, int]]:
    """(应返还总数, 逐日购买次数)。纯计算, 不写库。"""
    days = purchases_by_day(db, player_id)
    state = snapshot.get("power_buy") or {}
    if state:
        # snapshot 的 day 与键里的 day 同一口径(task_period(1, now) 的日起点),
        # 所以同一天取较大值; 只赢在「账本缺行」这一种情况上。
        try:
            day, count = int(state.get("day", -1)), int(state.get("count", 0))
        except (TypeError, ValueError):
            day, count = -1, 0
        if count > 0:
            days[day] = max(days.get(day, 0), count)
    return sum(overcharge_for(count) for count in days.values()), days


def settle(db, player_id: int, snapshot: dict, now: int) -> int:
    """给这个角色发一封差价返还邮件, 返回这次实际入账的光辉(0 = 无需/已发过)。

    调用方负责事务; 邮件走 ``player_mail`` 的 source_key 唯一索引, 所以登录、重连、
    甚至运维手动重跑都只会成功一次。
    """
    amount, days = refund_amount(db, player_id, snapshot)
    if amount <= 0:
        return 0
    ensure_mail_schema(db)
    inserted = db.execute(
        """INSERT OR IGNORE INTO player_mail
        (player_id,sender,title,body,created_at,attachments,source_key)
        VALUES (?,?,?,?,?,?,?)""",
        (player_id, SENDER, TITLE, BODY.format(amount), int(now),
         json.dumps({str(BRILLIANCE): amount}), SOURCE % player_id)).rowcount
    if not inserted:
        LOGGER.info("power refund already minted player=%s amount=%s", player_id, amount)
        return 0
    LOGGER.info("power refund minted player=%s amount=%s days=%s",
                player_id, amount, dict(sorted(days.items())))
    return amount
