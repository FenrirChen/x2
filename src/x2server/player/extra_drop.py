"""资源本额外掉落 (客户端「限时掉落活动」E_ExtraDroop) —— 常驻 +100% 实现.

客户端 ``ActivityReal`` 里的活动类型 23 是 ``E_ExtraDroop`` (名字「限时掉落活动」), 由
``表-ExtraDroop`` 决定哪批关卡在活动期间拿额外掉落: 每行绑一组关卡 (``SectionGroup``),
带 掉落类型 (``DroopType``)、加成百分比 (``DroopUPParam``)、每日上限 (``NumLimit``) 和
刷新周期 (``RefreshCycle``)。资源本那几行是:

    100002  2130101-2130105 (金币本)   DroopType 4 E_GoldDroopUP   DroopUPParam [100]
    100003  2130201-2130205           DroopType 2 E_DroopUP       DroopUPParam [100]
    100004  2132001-2132005           DroopType 2 E_DroopUP       DroopUPParam [100]
    100005  2132101-2132105           DroopType 2 E_DroopUP       DroopUPParam [100]

``DroopUPParam`` 读作百分比 (100 = +100%), 与 ``NumLimit`` 一起构成官方口径的
「资源本额外掉落 + 每日限次」。

本模块只在**能用单一倍数无歧义覆盖整组**的行上做倍率: ``len(DroopUPParam) == 1`` 时把
该值套到整个 ``SectionGroup`` (上面四行), ``len(DroopUPParam) == len(SectionGroup)`` 时
逐关取自己的倍数。装备本那行 (100001, 2133101-2134110) 的 ``DroopUPParam`` 是 29 个值的
逐关数组, 与 100 个 ``SectionGroup`` 对不上 (``SectionChoice`` 的对应关系未经证实), 因此
**刻意跳过** —— 与 docs/DROP_RULES.md「DroopUPParam 单位未确认」的既有结论一致, 用
``max()`` 一律压成一个数会误伤只该拿一部分倍率的关卡, 不做这种猜测。

口径 (USER_DECISION 2026-10-13): 把这套加成做成**常驻** —— 上面这些关卡每天前
``NumLimit``(=10) 次结算, 该次产出再给一份 (即翻倍 / +100%)。真打一局 (``economy.settle``)
与扫荡 (``economy.settle_sweep``) 都算次数, 每次扫荡的每一局各算一次。

开关默认**关**: ExtraDroop 的数量口径在 docs/knowledge/rewards/section_reward_system.md
里被明确记为「触发与数量规则尚未证实, 暂不自动给付」, 默认打开会改掉资源本的既有产出金额
并让既有单元测试 (如 tests/unit/test_section_reward_system.py 钉死的 2130101/2130201 金额)
失效。因此本模块只在显式打开它的服务器上生效 (tools/local_game_server.py 传
``resource_double_drop=True``)。

刻意**不**广告活动目录 (``C2L_QueryActivity``) 与 ``ExtraDropData`` (860/861): 客户端因此
不会建出活动页, 也不显示「额外掉落 剩余次数」—— 加成只在结算时实际多发, 客户端的掉落
预览不会变成双份 (结算以服务端为准)。要显示 badge 需要另开活动中心的接线。
"""
import json

# DroopType 枚举 (客户端 ExtraDroopEDroopType): 1 额外礼包, 2 掉率UP, 3 掉落数量, 4 金币掉率.
# 1 是「额外礼包」(ExtraGiftID) 路线, 由 activity_runtime.extra_rewards 按活动周期发放,
# 不在本模块的「常驻倍率」口径里。
RATE_TYPES = (2, 3, 4)


def beijing_day(now):
    """东八区自然日序号, 与 activity_runtime.extra_rewards 的 day 口径一致。"""
    return (int(now) + 8 * 3600) // 86400


class ExtraDropService:
    """资源本常驻 +100% 掉落: 每关每天前 NumLimit 次结算产出翻倍.

    ``enabled=False`` 时整段短路 (不读表、不建表、``consume`` 恒回 0), 默认构造因此与
    改动前完全一致。
    """

    def __init__(self, economy, enabled=False):
        self.store, self.clock = economy.store, economy.clock
        self.enabled = bool(enabled)
        self.by_section: dict[str, dict] = {}
        if not self.enabled:
            return
        # 行取自客户端解析的 ``activity_rotation_catalog.json`` (ActivityReal/ExtraDroop
        # dump), 不取 ``drop_catalog.json`` 的工作簿版: 工作簿「表-ExtraDroop」页签漏掉了
        # 100005 的 DroopUPParam (空列表, 客户端是 [100]), 照工作簿读会静默少掉一组资源本。
        from importlib.resources import files
        data = json.loads(files("x2server").joinpath(
            "data/activity_rotation_catalog.json").read_text(encoding="utf-8"))
        # 只认资源本 (economy_catalog 的 daily_sections): 同一张表里的 216xxxx 行是活动关卡
        # 的额外掉落, 跟着活动日程走, 不在「资源本常驻双倍」的口径里。
        daily = {str(section) for section in economy.daily_sections}
        for row in data["tables"]["ExtraDroop"]:
            if int(row["DroopType"]["value"]) not in RATE_TYPES:
                continue
            params = [int(value) for value in row.get("DroopUPParam") or ()]
            sections = [int(section) for section in row.get("SectionGroup") or ()]
            limit = int(row.get("NumLimit") or 0)
            if limit <= 0 or not sections:
                continue
            entry_cycle = max(1, int(row.get("RefreshCycle") or 1))
            row_id = int(row["ID"])
            if len(params) == 1 and params[0] > 0:
                # 单一倍数: 整组关卡同一倍率 (金币本/材料本 100002-100005)。
                entry = {"row": row_id, "ratio": params[0], "limit": limit, "cycle": entry_cycle}
                for section in sections:
                    if str(section) in daily:
                        self.by_section[str(section)] = entry
            elif len(params) == len(sections):
                # 逐关倍数: 与 SectionGroup 一一对应。
                for section, ratio in zip(sections, params):
                    if ratio > 0 and str(section) in daily:
                        self.by_section[str(section)] = {"row": row_id, "ratio": ratio,
                                                         "limit": limit, "cycle": entry_cycle}
            # 其它长度 (装备本 100001 的 29 vs 100): 对应关系未证实, 不猜, 跳过。
        if not self.by_section:
            raise ValueError("no resource-dungeon ExtraDroop rows in the activity catalog")
        with self.store.db:
            self.store.db.execute('''CREATE TABLE IF NOT EXISTS extra_drop_usage (
                player_id INTEGER NOT NULL, day INTEGER NOT NULL, row_id INTEGER NOT NULL,
                used INTEGER NOT NULL, PRIMARY KEY(player_id, day, row_id))''')

    def consume(self, player_id, section) -> int:
        """符合额外掉落且当日次数未用完时记一次使用并返回加成百分比; 否则 0。

        返回值是「再给百分之几」: 100 表示再给一份 (翻倍)。调用方按
        ``count + count * ratio // 100`` 加发。计数与出货在同一个 sqlite 事务里
        (settle/settle_sweep 由 battle 的 ``with self.store.db`` 包住), 结算失败回滚时
        次数也会一并回滚。
        """
        if not self.enabled:
            return 0
        entry = self.by_section.get(str(section))
        if entry is None:
            return 0
        day = beijing_day(self.clock()) // entry["cycle"]
        row = self.store.db.execute(
            "SELECT used FROM extra_drop_usage WHERE player_id=? AND day=? AND row_id=?",
            (player_id, day, entry["row"])).fetchone()
        if row is not None and int(row[0]) >= entry["limit"]:
            return 0
        self.store.db.execute('''INSERT INTO extra_drop_usage VALUES (?,?,?,1)
            ON CONFLICT(player_id,day,row_id) DO UPDATE SET used=used+1''',
            (player_id, day, entry["row"]))
        return entry["ratio"]
