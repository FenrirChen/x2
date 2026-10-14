"""社团 (Club / 公会) 系统: PBS 读取端 (ClubReader) + TCP 操作端 (ClubService)。

背景
----
客户端社团页是**混合协议**: 读操作用 PBS HTTP (路由前缀 ``/ClubService.``, POST+JSON,
响应信封 {"error":"","code":0,"data":{...}}), 写/操作类动作走 TCP 游戏消息
(``C2L_*``/``L2C_*``, 号段 742..799, 见 protocol/recovered_ids.py)。抓包
logs/packets.jsonl 里用户进社团页发的 C2L_RecommandClub(744)/C2L_CreateClub(742) 当时
没有任何回包 —— 服务端根本没实现社团。本文件把社团做出来。

照抄的既有模式
-------------
* ClubReader 照 player/social.py 的 SocialReader: 自带
  ``sqlite3.connect(path, check_same_thread=False, timeout=10)``、``ensure_*_schema``、
  ``close()``、``handle(path,args,player_id,now)`` 分发。HTTP worker 线程必须有自己的连接,
  绝不能共用事件循环的 PlayerStore.db。
* ClubService 照 player/mail.py 的 MailService: ``handlers()`` 返回
  {"C2L_X": self.handle}, handle 内用 ``CORE_MESSAGE_REGISTRY.name_for`` 取消息名再
  ``CLUB_SCHEMAS[name].decode``。

JSON 键名
---------
PBS 回包键用客户端 C# DTO 的成员名本身 (PascalCase, 见 work/cpp/appdata/il2cpp-types.h:
``ClubData._MemberList_k__BackingField`` -> ``MemberList``)。客户端 Newtonsoft 反序列化
大小写不敏感但**不忽略下划线**, 所以键不能带下划线 —— 已验证可工作的 mail.py 用 camelCase、
social.py 用 PascalCase。离线参考 x2offline/src/server/pbs_replies.inc 用的是 snake_case,
那是更老的口径, 不可照抄键名。PBS 请求参数则是 snake_case (与已上线的 mail 路由一致)。

人机
----
复用 social.ai_roster() (data/ai_players.json, 39 条)。社团成员=玩家 + 名册前 20 个人机。
"""
from __future__ import annotations

import json
import random
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from x2server.messages.club import CLUB_SCHEMAS, SIMPLE_CLUB_DATA
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

from .economy import UnresolvedEconomy
from .server_clock import day_index, day_period
from .social import ai_roster

# 客户端 ClubPost__Enum (il2cpp-types.h): Member 0 / Director 1 / VicePresident 2 / President 3。
CLUB_POST_MEMBER = 0
CLUB_POST_PRESIDENT = 3
# 客户端 ClubJoinType__Enum: Unlimited 0 / Confirm 1 / RejectAll 2 / Mixed 3。
CLUB_JOIN_UNLIMITED = 0

# 默认社团 (P1): id = 1000+player_id, 成员=玩家+全部人机名册。社团 id 段取 1000,
# 推荐列表另用 2000 段, 两者不重叠。
DEFAULT_CLUB_BASE = 1000
RECOMMEND_BASE = 2000
DEFAULT_CLUB_NAME = "解神者"
RECOMMEND_COUNT = 6
CLUB_MEM_LIMIT = 50

# 社团成员 = 玩家 + 全部人机名册 (data/ai_players.json 的 40 人)。
# 用户要求「社团要填满人数」, 所以社团不再只取名册前 20 个人机, 而是把能用的全部拉进来
# (玩家 + 40 人机 = 41 人; 客户端上限按实际成员数下发, 所以显示成满员 41/41)。
# 已经铺过的成员名册版本。1 = 只铺了名册前 20 个人机; 2 = 铺满全部人机名册。
# 存量档升到该版本时会一次性补齐到满员; 升过一次后就不再补, 免得玩家手动踢掉的成员
# 又被自动加回来。
ROSTER_VERSION = 2

# 客户端 ClubModule.GetSelfClub / GetSelfClubCallback (0x01561D80 / 0x01580BF8) 拿回
# 自己的社团后, 会从 ClubData.Meta 里取 "clubGroupChatUUID" 并**无 null 守卫**地解引用
# 返回的 pbs.Value (取 VInt64); GetClubLevel (0x01567E8C) 同样无守卫地取 "clubLevel"。
# Meta 里缺任一项 -> NullReferenceException, 社团页永远打不开(客户端还会重试 GetClub)。
CLUB_META_GROUP_CHAT_UUID = "clubGroupChatUUID"
CLUB_META_LEVEL = "clubLevel"
CLUB_META_MEM_LIMIT = "clubMemLimit"
# 社团图标 (界面上方那张方形头像)。ClubData/ClubSimpleData 都没有 Icon 字段,
# 客户端是走 ClubModule.GetClubMetaValue("clubIconId") 再交给 GuildPictureManager
# 取图的 (见 work/stringliterals.csv 的 StringLiteral_clubIconId, 以及
# ClubIconSetting$$Refresh 的调用图)。Meta 里没有这个键 -> 头像永远空白。
CLUB_META_ICON = "clubIconId"
# 默认社团图标 = GuildPicture 表的第一条 GuildPictureID (work/_tables/all_parsed/GuildPicture.json,
# 1270004/1270005/1270006...)。icon 为 0 时用它, 否则客户端取不到图。
DEFAULT_CLUB_ICON = 1270004
# 镜域试炼 boss 血条: 客户端剩余血量 = 它自己算出的上限 - Meta["clubDamage_{层号}"]
# (ClubModule_GetClubBossHP 0x01564B7C: 键 = String_Format("clubDamage_{0}",
# GetClubActivityLayer()+1); 没有 clubLayer_* 时 GetClubActivityLayer 返回 0, 所以第一层
# 读的是 clubDamage_1)。不发这个键 -> 血条永远是满的 (用户实测「打完 boss 血量没变」)。
CLUB_META_DAMAGE = "clubDamage_"
# 社团「今日活动积分」: 社团页左上角每日宝箱的进度 (0/300000) 读的就是它 (键名见
# work/stringliterals.csv 的 StringLiteral_clubTodayScore)。分母 300000 =
# GuildLevel.Level1.DailyScore。以前完全不下发这个键 -> 进度恒 0 (用户实测「宝箱没计算」)。
CLUB_META_TODAY_SCORE = "clubTodayScore"

# ---- 公会助力页 (KVStoreService.GetValuesV2, club_speed_*) ----------------
# 客户端 CollegeModule_SendClubBuildHelpedInfo (0x1AF4E48) 对每个成员拼两个键:
# ``club_speed_<uid>_1`` (建筑) 与 ``club_speed_<uid>_2`` (奇迹)。回包每条 val 被
# CollegeModule.GetAllBuildHelpInfo (0x1B023BC) 按 CollegeModule.HelpedBuildingData
# {buildId,upgradeEndTime,buildLevel} 反序列化。字面量出处 work/stringliterals.csv
# L16743-16745 ('club_speed_', '_1', '_2')。
CLUB_HELP_KEY = "club_speed_"
# slot -> 客户端 CollegeLevel 表里的合法建造 id。**必须是真实存在的表行**: 客户端
# SendHelpBuidInfoAll 会对 buildId 调 CollegeModule.GetTableData 且不判空 (为空直接抛),
# 用假 id 会崩。701..708 = 建筑, 721..728 = 奇迹 (见 data/college_catalog.json 的 baseType)。
HELP_BUILD_IDS = {1: (701, 702, 703, 704, 705, 706, 707, 708),
                  2: (721, 722, 723, 724, 725, 726, 727, 728)}

# 祈愿 (P3)。
AI_WISH_COUNT = 6          # 人机每天挂的待捐祈愿条数 (玩家可以捐它们拿资源)
AI_WISH_DONORS = 3         # 玩家发愿后会来助力的人机数 (每人 1~2 个)
AI_WISH_DELAY_MIN = 60     # 助力不是"一发就到": 最快 60 秒后才到账
AI_WISH_DELAY_STEP = 30    # 第 2/3 个人机再各晚 30 秒 (60/90/120s)
WISH_WANT_NUM = 2
DONATE_MIN_QTY = 2         # 只有当玩家背包有 >=2 个可堆叠材料时, AI 才挑它当祈愿道具
DEFAULT_WISH_ITEM = 1201003  # 贝黑莫斯碎片 (ItemType 12 E_Chip); 背包无材料时的兜底祈愿物
DONATE_GOLD = 200          # 玩家给人机捐一次: 少量金币 (item 1237901)
DONATE_SCORE = 10          # 玩家给人机捐一次: 社团积分 (加入 clubs.cur_score/total_score)
RECEIVE_REWARD_GOLD = 500  # 社团活动领奖 (P4): 金币

# 镜域试炼 (P4): 玩家每次挑战结算后, 全体人机各**跟打 1 次**, 单次伤害 = 玩家本局
# **真实伤害** × [MIRROR_AI_RATIO_MIN, MIRROR_AI_RATIO_MAX] 随机 (用户口径「玩家打完
# 一次后人机 player 也会打一次, 伤害通常是玩家的 120%~150%, 之前的太低了」)。这份成绩
# 累加进成员伤害榜与活动积分榜, 但**不扣 boss 血** (见 settle_mirror_checkout)。
# DEFAULT_MIRROR_DAMAGE 是没有基准时的默认值。
MIRROR_AI_RATIO_MIN = 1.2
MIRROR_AI_RATIO_MAX = 1.5
DEFAULT_MIRROR_DAMAGE = 1000

# 玩家单次镜域挑战的伤害基准。客户端**会上报真实伤害**: 887 (C2L_CheckoutMainMission)
# 的 field 13 antiCheat 里逐英雄 useSkillDamage.damageNum 之和 (回退 field 28 hp)。
# 抓包 2026-10-12 镜域 sec 2170001 实测 26,970,889。所以结算用真实值; 下面这个常量只在
# 拿不到真实值时兜底 (例如 PostClubBattle 这种不带 887 的路径、或旧存档重放)。
MIRROR_DAMAGE_PER_RUN = 1_500_000

# 镜域伤害 -> 社团/成员「活动积分」的换算比 (本地自造, 官方换算表未反出)。抓包单次真实
# 伤害约 2700 万 -> 约 2700 分; 全团(21 人机 + 玩家)一天合计约 7 万 -> 每日集体宝箱
# 300000 的目标约 4 次挑战打满。
MIRROR_SCORE_DIV = 10_000

# 新社团铺成员名册时的初始镜域成绩 (club_members.damage)。以前写的是 DEFAULT_MIRROR_DAMAGE
# (1000), 而活动积分 = damage // MIRROR_SCORE_DIV = 0, 于是新社团「成员详情 → 7 日积分」
# 全是 0 (用户实测; 社团 1002 全员 damage=1000/week_score=0)。改成按"一次镜域挑战"的量级
# 起步, 再乘 uid 派生的确定性抖动拉开差距。
ROSTER_SEED_DAMAGE = MIRROR_DAMAGE_PER_RUN


def _score_jitter(uid: str) -> float:
    """老库回填成绩时的确定性抖动系数 [1.0, 1.4)。

    老代码给全体人机写的是**同一个** damage 值, 直接换算会让积分榜排成一条直线 (用户实测
    「现在全都是一样的」)。这里按 uid 派生一个稳定系数把这些历史值拉开。不用内置 ``hash()``:
    ``PYTHONHASHSEED`` 每次启动都变, 那样每次重启积分又会换一批。
    """
    h = 0
    for ch in uid:
        h = (h * 131 + ord(ch)) & 0xFFFF_FFFF
    return 1.0 + (h % 4000) / 10_000.0


def _seed_member(uid: str) -> tuple[int, int]:
    """新成员的初始 (镜域累计伤害, 活动积分)。

    活动积分 = 伤害 // MIRROR_SCORE_DIV; 用 uid 派生的确定性抖动让同团成员各自不同,
    不会排成一条直线。保证积分非 0, 否则成员详情的「7 日积分」又回到 0。
    """
    damage = int(ROSTER_SEED_DAMAGE * _score_jitter(uid))
    return damage, damage // MIRROR_SCORE_DIV


GOLD_ITEM = 1237901        # economy.CURRENCIES 里的金币号
CLUB_SCORE_ITEM = 1237924  # 学级积分道具 (ItemType 16); login.PROFILE_CURRENCIES 的 GuildScore 从背包回填

# ---- 社团玩法参数 (依据客户端表 + 官方玩法攻略) ---------------------------
CLUB_OPEN_LEVEL = 17       # 客户端 FunctionOpen: source_id 17 / level 17 解锁「社团」(21960)
MIRROR_DAILY_REGEN = 3     # 镜域试炼: 每日恢复 3 次挑战次数
MIRROR_MAX_COUNT = 5       # 镜域试炼: 次数上限 5 (溢出不再恢复)
WISH_DAILY_LIMIT = 1       # 祈愿墙每日发布次数兜底 (官方 GuildWish 表有 NumLimit 时按表)
GOLD_CURRENCY_ENUM = 901   # 客户端 CurrencyTypeECurrencyEnu 里的金币 (背包 item 1237901)
CREATE_CLUB_COST = 1000    # 建立社团消耗金币 (官方表无费用字段, 本地自造, 见攻略"少量金币")
FIRST_CLEAR_GIFT = 778201  # 首通尘封宝箱兜底 (= club_catalog.mirror[*].challengeReward)
DAILY_SCORE_GIFT = 778202  # 每日集体积分达标宝箱 (= GuildLevel Lv1 DailyAward)
CHIP_ITEM_TYPE = 12        # ItemType E_Chip: 神格碎片

CODE_OK = 10
CODE_REFUSED = 13

# 客户端 ServerTime__cctor 里写死的时间常量 (2018-01-01 00:00 北京); 社团祈愿记录的
# Time 走 "2018 标度", 下发前要加上它 (见 wishing_history / ClubWishHistory 的注释)。
_TO_2018 = 1514736000


def ensure_club_schema(db) -> None:
    """社团/成员/祈愿/捐赠/活动 五张表; 幂等 (HTTP 线程与事件循环共用一份定义)。"""
    db.execute("""CREATE TABLE IF NOT EXISTS clubs (
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, desc TEXT NOT NULL DEFAULT '',
        notice TEXT NOT NULL DEFAULT '', owner TEXT NOT NULL,
        type INTEGER NOT NULL DEFAULT 0, icon INTEGER NOT NULL DEFAULT 0,
        history_score INTEGER NOT NULL DEFAULT 0, total_score INTEGER NOT NULL DEFAULT 0,
        cur_score INTEGER NOT NULL DEFAULT 0, week_score INTEGER NOT NULL DEFAULT 0,
        reset_week_time INTEGER NOT NULL DEFAULT 0, total_medal INTEGER NOT NULL DEFAULT 0,
        round_medal INTEGER NOT NULL DEFAULT 0, create_time INTEGER NOT NULL DEFAULT 0,
        apply_level INTEGER NOT NULL DEFAULT 1, auto_level INTEGER NOT NULL DEFAULT 1)""")
    db.execute("""CREATE TABLE IF NOT EXISTS club_members (
        club_id INTEGER NOT NULL, uid TEXT NOT NULL, post INTEGER NOT NULL DEFAULT 0,
        score INTEGER NOT NULL DEFAULT 0, week_score INTEGER NOT NULL DEFAULT 0,
        history_score INTEGER NOT NULL DEFAULT 0, medal INTEGER NOT NULL DEFAULT 0,
        round_medal INTEGER NOT NULL DEFAULT 0, damage INTEGER NOT NULL DEFAULT 0,
        time INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (club_id, uid))""")
    db.execute("""CREATE TABLE IF NOT EXISTS club_wishes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, club_id INTEGER NOT NULL,
        owner_uid TEXT NOT NULL, item_id INTEGER NOT NULL, want_num INTEGER NOT NULL DEFAULT 0,
        donate_num INTEGER NOT NULL DEFAULT 0, got_num INTEGER NOT NULL DEFAULT 0,
        limit_num INTEGER NOT NULL DEFAULT 0, donate_count INTEGER NOT NULL DEFAULT 0,
        time INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS club_wish_donations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, wish_id INTEGER NOT NULL,
        donor_uid TEXT NOT NULL, num INTEGER NOT NULL DEFAULT 0,
        time INTEGER NOT NULL DEFAULT 0, received INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE IF NOT EXISTS club_activity (
        player_id INTEGER PRIMARY KEY, club_id INTEGER NOT NULL DEFAULT 0,
        challege_count INTEGER NOT NULL DEFAULT 0, received_layer TEXT NOT NULL DEFAULT '',
        score_reward_flag INTEGER NOT NULL DEFAULT 0, battled_sections TEXT NOT NULL DEFAULT '',
        damage INTEGER NOT NULL DEFAULT 0)""")
    # 镜域试炼每日恢复次数用的"上次恢复日" (本地日, 见 server_clock.day_index)。
    # 老库补列; 与 player/battle.py 的 _add_column 同一套写法。
    _add_column(db, "club_activity", "regen_day", "INTEGER NOT NULL DEFAULT 0")
    # 本日已消耗的挑战次数。用来区分"今天还没打过"与"打完了才剩这么点":
    # 前者次数没满说明是旧库把初值写成 3 的遗留, 由 mirror_count 补满 (用户实测 3/5)。
    _add_column(db, "club_activity", "battled_count", "INTEGER NOT NULL DEFAULT 0")
    # 公会镜域血池 (P4): "层号:累计伤害,..."。由 _club_meta 以 clubDamage_{层号} 下发,
    # 客户端的 boss 剩余血量 = 上限 - 该值。
    _add_column(db, "club_activity", "mirror_damage", "TEXT NOT NULL DEFAULT ''")
    # 已铺过的成员名册版本 (1 = 只铺了名册前 20 个人机)。
    _add_column(db, "clubs", "roster_version", "INTEGER NOT NULL DEFAULT 0")
    # 社团今日活动积分 (本地日口径)。客户端左上角每日宝箱进度 = Meta["clubTodayScore"]。
    # day_score_day 记这份积分属于哪个本地日, 跨日后读作 0 (惰性归零, 见 club_today_score)。
    _add_column(db, "clubs", "day_score", "INTEGER NOT NULL DEFAULT 0")
    _add_column(db, "clubs", "day_score_day", "INTEGER NOT NULL DEFAULT 0")
    # 一次性回填: 老库的 week_score/history_score 从来没被写过 (恒 0), 于是社团/成员积分榜
    # 一片 0 (用户实测图二)。按已累计的 damage 换算补上, 之后由 _add_member_activity 增量维护。
    # 人机行还要再拉开: 老代码给全体人机写的是**同一个** damage, 直接换算会排成一条直线
    # (用户实测「现在全都是一样的」), 所以人机额外乘一个由 uid 派生的确定性抖动
    # (_score_jitter); 玩家自己的行是真实成绩, 不动。
    # score_ver 记住"这行已经换算过": 换算过一次就置 1, 保证只跑一次 —— 否则每次启动都会
    # 再乘一次抖动, damage 一路膨胀。
    _add_column(db, "club_members", "score_ver", "INTEGER NOT NULL DEFAULT 0")
    rows = db.execute("""SELECT club_id, uid, damage FROM club_members
        WHERE score_ver=0 AND damage>=?""", (MIRROR_SCORE_DIV,)).fetchall()
    for row in rows:
        uid = str(row["uid"])
        damage = int(row["damage"])
        if uid.startswith("ai"):
            damage = int(damage * _score_jitter(uid))
        db.execute("""UPDATE club_members SET damage=?, week_score=?, history_score=?
            WHERE club_id=? AND uid=?""",
            (damage, damage // MIRROR_SCORE_DIV, damage // MIRROR_SCORE_DIV,
             row["club_id"], uid))
    db.execute("UPDATE club_members SET score_ver=1 WHERE score_ver=0")
    # 修复"种子行": 老代码给新建社团的成员写的初值 damage=DEFAULT_MIRROR_DAMAGE(1000),
    # 换算出的活动积分恒为 0, 而上面那次回填要求 damage>=MIRROR_SCORE_DIV、且 score_ver 已
    # 置 1 不会再跑, 于是这些行永远停在 0 (用户实测「成员详情 7 日积分一直是 0」)。
    # 这里把仍停在旧初值 (damage < MIRROR_SCORE_DIV) 且积分为 0 的行重新种一遍。种完
    # damage >= MIRROR_SCORE_DIV, 条件不再成立 -> 幂等, 每次启动都能修但不重复放大。
    stale = db.execute("""SELECT club_id, uid FROM club_members
        WHERE week_score=0 AND damage < ?""", (MIRROR_SCORE_DIV,)).fetchall()
    for row in stale:
        damage, points = _seed_member(str(row["uid"]))
        db.execute("""UPDATE club_members SET damage=?, week_score=?, history_score=?
            WHERE club_id=? AND uid=?""", (damage, points, points, row["club_id"], row["uid"]))


def _add_column(db, table: str, name: str, declaration: str) -> None:
    """表里没有这一列时补上 (幂等迁移)。"""
    if name not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


# ---- 共享工具 (ClubReader / ClubService 都用) -----------------------------

def player_uid(player_id: int) -> str:
    """玩家在社团里的 uid。人机 uid 是 "aiXXXX"; 玩家用存档 player_id 的十进制串。"""
    return str(player_id)


def club_uid(uid: Any) -> str:
    """库内 uid -> 对外的数字 uid (社团成员/祈愿/捐赠者/历史全都用它)。

    客户端 ClubModule.GetWishingCallback 对 ``ClubMemberWishing.Userid`` 调
    ``Int64_TryParse``, **解析失败就静默跳过整行** —— 旧实现直接下发 "ai1003", 于是
    人机的祈愿与助力行全被丢掉, 祈愿页/助力页一片空白 (用户两次实测)。另一处
    ``ClubModule.GetMemberByUserID(String userId)`` 又是拿字符串全等去比对
    ``ClubMember.Userid``, 所以两边必须用同一套数字串: 人机 "ai1003" -> "1003"
    (后缀在 ai_players.json 里唯一), 玩家 "1" 原样返回。
    """
    text = str(uid)
    if text[:2] == "ai" and text[2:].isdigit():
        return text[2:]
    return text


_AI_UID_BY_NUM: dict[str, str] | None = None


def _ai_uid_by_num() -> dict[str, str]:
    """数字 uid -> 库内人机 uid ("1003" -> "ai1003"), 供写接口反查。"""
    global _AI_UID_BY_NUM
    if _AI_UID_BY_NUM is None:
        mapping: dict[str, str] = {}
        for entry in ai_roster():
            uid = str(entry["uid"])
            if uid[:2] == "ai" and uid[2:].isdigit():
                mapping.setdefault(uid[2:], uid)
        _AI_UID_BY_NUM = mapping
    return _AI_UID_BY_NUM


def db_uid(uid: Any) -> str:
    """对外数字 uid -> 库内 uid (写接口 optedId / member 反查)。查不到就原样返回。"""
    text = str(uid or "")
    return _ai_uid_by_num().get(text, text)


def parse_help_key(key: Any) -> tuple[str, int] | None:
    """``club_speed_<uid>_<slot>`` -> (uid, slot); 不是助力键就 None。

    uid 本身可能含下划线吗? 不会 —— 库里 uid 只会是玩家十进制串或 aiXXXX, 所以按
    "前缀 + 末尾 ``_<slot>``" 解析是安全的 (rpartition 取最后一段作 slot)。
    """
    text = str(key or "")
    if not text.startswith(CLUB_HELP_KEY):
        return None
    body = text[len(CLUB_HELP_KEY):]
    uid, sep, slot = body.rpartition("_")
    if not sep or slot not in ("1", "2"):
        return None
    if not uid:
        return None
    return uid, int(slot)


def help_building_value(uid: str, slot: int, now: float) -> dict[str, Any]:
    """人机成员的一条"建造中"行 (HelpedBuildingData), 由 uid+slot 派生, 稳定可复现。

    ``upgradeEndTime`` 必须落在**将来**: 客户端 GetShowHelpInfo (0x1B02C30) 会算
    TimeSpan 剩余秒数, ``<= 0`` 的行直接不上助力列表 (b.ls 跳过分支)。偏移按 uid 派生
    成 1~10 小时, 让各成员的倒计时看起来各不相同。
    """
    ids = HELP_BUILD_IDS[2 if slot == 2 else 1]
    h = 0
    for ch in f"{uid}:{slot}":
        h = (h * 131 + ord(ch)) & 0xFFFF_FFFF
    return {"buildId": ids[h % len(ids)],
            "upgradeEndTime": int(now) + 3600 + (h % 9) * 3600,
            "buildLevel": 1 + (h // 17) % 12}


def _damage_map(text: Any) -> dict[int, int]:
    """club_activity.mirror_damage ("层号:伤害,...") -> {层号: 累计伤害}。"""
    out: dict[int, int] = {}
    for part in str(text or "").split(","):
        key, _, value = part.partition(":")
        if not key.strip().isdigit():
            continue
        try:
            out[int(key)] = int(value)
        except (TypeError, ValueError):
            continue
    return out


def _damage_text(pool: dict[int, int]) -> str:
    return ",".join(f"{layer}:{int(pool[layer])}" for layer in sorted(pool) if int(pool[layer]) > 0)


def roster_entry(uid: str) -> dict[str, Any] | None:
    for entry in ai_roster():
        if entry["uid"] == uid:
            return entry
    return None


def club_roster() -> list[dict[str, Any]]:
    """社团里的人机成员 = 全部人机名册 (data/ai_players.json, 按 uid 去重)。

    用户要求「社团要填满人数」: 以前只取前 20 人, 现在把名册里能用的全部拉进社团
    (玩家 + 40 人机 = 41 人)。
    """
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in ai_roster():
        if entry["uid"] not in seen:
            entries.append(entry)
            seen.add(entry["uid"])
    return entries


def _attrib(uid: str, name: str, head: int, level: int, online: bool = True) -> dict[str, Any]:
    """BaseAttrib (pbs) —— 与 SocialReader._attrib 同形, 客户端按同一套成员解析。

    ``Ext`` 不能空: 社团成员节点 (ClubMemberNode_RefreshItem 0x01577B78) 与积分榜
    (ClubRankNode_RefreshItem 0x01579E30) 是从 ``Attrib.Ext["iconID"]`` 取头像的
    (见 work/stringliterals.csv 的 StringLiteral_iconID)。旧实现恒发 ``Ext: {}``
    -> 每个成员的头顶图标都取不到, 头像空白。iconID 就是头图标号 (head)。
    """
    return {"Uid": uid, "CreateTime": 0, "Name": name, "Head": str(head), "Level": level,
            "Zone": "", "Server": "local", "Channel": "local", "SubChannel": "", "Os": "",
            "Online": online,
            "Ext": {"iconID": str(head), "firstMedal": "0", "FramePicId": "0",
                    "lastLogoutTime": "0"}}


def club_id_of(db, player_id: int) -> int:
    row = db.execute("SELECT club_id FROM club_members WHERE uid=?",
                     (player_uid(player_id),)).fetchone()
    return int(row[0]) if row is not None else 0


def _ensure_roster_members(db, club_id: int, now: float) -> None:
    """把社团成员补到满员 (一次性, 由 clubs.roster_version 记版本)。

    存量档是旧口径铺的 (如"玩家 + 前 20 个人机"); 这里在第一次读到这个社团时把缺的人机
    一次性补齐到 club_roster() 的全部 (40 人机), 并记下版本 —— 之后再读到就跳过,
    玩家手动踢掉的成员不会被自动加回来。调用方负责加锁/事务。
    """
    row = db.execute("SELECT roster_version FROM clubs WHERE id=?", (club_id,)).fetchone()
    if row is None or int(row[0]) >= ROSTER_VERSION:
        return
    for index, entry in enumerate(club_roster()):
        damage, points = _seed_member(entry["uid"])
        db.execute("""INSERT OR IGNORE INTO club_members
            (club_id,uid,post,damage,week_score,history_score,time)
            VALUES (?,?,?,?,?,?,?)""",
            (club_id, entry["uid"], CLUB_POST_MEMBER, damage, points, points, int(now) + index + 1))
    db.execute("UPDATE clubs SET roster_version=? WHERE id=?", (ROSTER_VERSION, club_id))


def ensure_membership(db, player_id: int, now: float) -> int:
    """玩家还没入团时把他加进默认社团 (1000+player_id) 并铺好成员。

    证据 (P1): 客户端进社团页期望的直接就是"我的社团", 未入团时 GetClub 会拿到空对象、
    推荐页也空。首次请求自动入团 = 玩家立刻是成员。调用方负责加锁/事务。
    """
    existing = club_id_of(db, player_id)
    if existing:
        _ensure_roster_members(db, existing, now)
        return existing
    club_id = DEFAULT_CLUB_BASE + player_id
    db.execute("""INSERT OR IGNORE INTO clubs (id,name,desc,notice,owner,type,create_time,roster_version)
        VALUES (?,?,?,?,?,?,?,?)""",
        (club_id, DEFAULT_CLUB_NAME, "", DEFAULT_CLUB_NAME, player_uid(player_id),
         CLUB_JOIN_UNLIMITED, int(now), ROSTER_VERSION))
    damage, points = _seed_member(player_uid(player_id))
    db.execute("""INSERT OR IGNORE INTO club_members
        (club_id,uid,post,damage,week_score,history_score,time)
        VALUES (?,?,?,?,?,?,?)""",
        (club_id, player_uid(player_id), CLUB_POST_PRESIDENT, damage, points, points, int(now)))
    for index, entry in enumerate(club_roster()):
        damage, points = _seed_member(entry["uid"])
        db.execute("""INSERT OR IGNORE INTO club_members
            (club_id,uid,post,damage,week_score,history_score,time)
            VALUES (?,?,?,?,?,?,?)""",
            (club_id, entry["uid"], CLUB_POST_MEMBER, damage, points, points, int(now) + index + 1))
    return club_id


def join_club(db, player_id: int, club_id: int, now: float) -> int:
    """玩家换团: 先移除旧成员行, 再把目标团 (不存在则按推荐列表物化) 补上。调用方加锁。"""
    if club_id <= 0:
        club_id = DEFAULT_CLUB_BASE + player_id
    row = db.execute("SELECT id FROM clubs WHERE id=?", (club_id,)).fetchone()
    if row is None:
        rec = next((c for c in recommend_clubs(now) if c["id"] == club_id), None)
        name = rec["name"] if rec else f"社团{club_id}"
        owner = rec["owner"] if rec else player_uid(player_id)
        db.execute("""INSERT OR IGNORE INTO clubs (id,name,desc,notice,owner,type,create_time)
            VALUES (?,?,?,?,?,?,?)""",
            (club_id, name, "", name, owner, CLUB_JOIN_UNLIMITED, int(now)))
    db.execute("DELETE FROM club_members WHERE uid=?", (player_uid(player_id),))
    damage, points = _seed_member(player_uid(player_id))
    db.execute("""INSERT OR IGNORE INTO club_members
        (club_id,uid,post,damage,week_score,history_score,time)
        VALUES (?,?,?,?,?,?,?)""",
        (club_id, player_uid(player_id), CLUB_POST_PRESIDENT, damage, points, points, int(now)))
    # 补人机名册: 推荐社团宣传的是 5~14 人 (recommend_clubs 的 member_num), 只插玩家会得到
    # 一个只有 1 人的空社团页 (成员详情 / 7 日积分全空)。与 ensure_membership 同款铺法。
    for index, entry in enumerate(club_roster()):
        damage, points = _seed_member(entry["uid"])
        db.execute("""INSERT OR IGNORE INTO club_members
            (club_id,uid,post,damage,week_score,history_score,time)
            VALUES (?,?,?,?,?,?,?)""",
            (club_id, entry["uid"], CLUB_POST_MEMBER, damage, points, points, int(now) + index + 1))
    return club_id


def member_uids(db, club_id: int) -> list[str]:
    return [str(row[0]) for row in db.execute(
        "SELECT uid FROM club_members WHERE club_id=? ORDER BY post DESC, time, uid", (club_id,))]


def donatable_items(db, player_id: int, economy) -> list[int]:
    """玩家背包里**真实存在且数量≥2**的可堆叠材料 —— AI 祈愿物就从这里挑。

    这样客户端「赠送」按钮才可点 (它按背包数量判可捐)。背包里没有时返回空列表,
    调用方回退到 DEFAULT_WISH_ITEM。
    """
    rows = db.execute("SELECT item_id,quantity FROM inventory WHERE player_id=? AND quantity>=?",
                      (player_id, DONATE_MIN_QTY)).fetchall()
    items = []
    for row in rows:
        item_id = int(row[0])
        if economy is not None:
            info = economy.items.get(item_id) or {}
            if info.get("ItemType", {}).get("value") not in economy.STACKABLE_REWARD_TYPES:
                continue
        items.append(item_id)
    return sorted(items)


_WISH_CATALOG_CACHE: dict[int, dict] | None = None


def wish_catalog() -> dict[int, dict]:
    """祈愿道具白名单 = 官方 GuildWish 表 (data/club_catalog.json 的 wishes 段, 61 条)。

    客户端渲染祈愿列表时按 ItemId 反查 GuildWish 表, 查不到就报
    「GuildWish表不存在{0}」/「GuildWish 表配置WishConsume错误 ID{0}」并中断整页渲染
    —— 用户实测的"祈愿页一片空白"就是旧代码把 1101050/1201000 这些**不在表里**的道具
    当成了祈愿物。所以下发的每一条祈愿 (人机的与玩家自己的) ItemId 都必须在这张表里。
    """
    global _WISH_CATALOG_CACHE
    if _WISH_CATALOG_CACHE is None:
        path = Path(__file__).resolve().parent.parent / "data" / "club_catalog.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            _WISH_CATALOG_CACHE = {int(k): v for k, v in (doc.get("wishes") or {}).items()}
        except (OSError, ValueError, TypeError):
            _WISH_CATALOG_CACHE = {}
    return _WISH_CATALOG_CACHE


def wish_num_limit(item_id: int) -> int:
    """该祈愿物的每日收取上限 (GuildWish.NumLimit); 表里没有时退回 WISH_WANT_NUM。"""
    entry = wish_catalog().get(int(item_id)) or {}
    try:
        return max(1, int(entry.get("numLimit", WISH_WANT_NUM)))
    except (TypeError, ValueError):
        return WISH_WANT_NUM


def wish_daily_limit(item_id: int) -> int:
    """该祈愿物每日可发布几次 (攻略: 1/2 星神格 3 次, 3 星神格 2 次)。

    次数就写在官方 GuildWish 表的 NumLimit 上 (1201003/1201004 = 3, 1201005 = 2 …),
    表里没有时退回 WISH_DAILY_LIMIT。客户端发布按钮的置灰也读同一个值。
    """
    entry = wish_catalog().get(int(item_id)) or {}
    try:
        return max(1, int(entry.get("numLimit", WISH_DAILY_LIMIT)))
    except (TypeError, ValueError):
        return WISH_DAILY_LIMIT


def wish_consume(item_id: int) -> int:
    """发布该祈愿物要花多少金币 (官方 GuildWish.Consume = [901(金币), 数量])。

    客户端渲染祈愿行时会按同一张表把 Consume 画成"消耗 金币×N"; 表里没有/格式不对
    时返回 0 (不收费), 让发布仍然可用。
    """
    entry = wish_catalog().get(int(item_id)) or {}
    consume = entry.get("consume") or []
    try:
        if len(consume) >= 2 and int(consume[0]) == GOLD_CURRENCY_ENUM:
            return max(0, int(consume[1]))
    except (TypeError, ValueError):
        pass
    return 0


def ensure_ai_wishes(db, club_id: int, player_id: int, economy, now: float) -> None:
    """人机每天挂一批待捐祈愿, 供玩家捐赠换资源 (幂等: 每个本地日只铺一次)。

    用户口径: 「人机 player 每天会自动祈愿随机神格碎片/物品供玩家获得资源」。
    所以每个本地日给人机重新铺 ``AI_WISH_COUNT`` 条, 上一日的人机祈愿连同其捐赠
    记录一并清掉, 免得越积越多 (玩家自己发的祈愿不动)。调用方负责加锁/事务。

    道具只能从 ``wish_catalog()`` (官方 GuildWish 表) 里挑: 旧实现直接拿玩家背包里的
    任意材料, 混进了 1101050/1201000 这种不在表里的 id, 客户端查表失败 -> 整页空白。
    只要**任意**一条 (含往日遗留、含玩家自己发的) item_id 不在表里, 就把库里的非法行
    连同其捐赠记录清掉再重建人机的当日祈愿 —— 否则旧脏行会一直留着, 页面永远拉不出来。
    今日人机祈愿齐全且全部合法时直接返回。
    """
    start, _ = day_period(int(now))
    catalog = wish_catalog()
    rows = db.execute(
        "SELECT id, owner_uid, item_id, time FROM club_wishes WHERE club_id=?",
        (club_id,)).fetchall()
    illegal = [int(r["id"]) for r in rows if int(r["item_id"]) not in catalog]
    today_ai = [int(r["item_id"]) for r in rows
                if str(r["owner_uid"]).startswith("ai") and int(r["time"]) >= start]
    if today_ai and not illegal:
        return
    for wish_id in illegal:
        db.execute("DELETE FROM club_wish_donations WHERE wish_id=?", (wish_id,))
        db.execute("DELETE FROM club_wishes WHERE id=?", (wish_id,))
    stale = [row[0] for row in db.execute(
        "SELECT id FROM club_wishes WHERE club_id=? AND owner_uid LIKE 'ai%'", (club_id,))]
    for wish_id in stale:
        db.execute("DELETE FROM club_wish_donations WHERE wish_id=?", (wish_id,))
    db.execute("DELETE FROM club_wishes WHERE club_id=? AND owner_uid LIKE 'ai%'", (club_id,))
    pool = [item_id for item_id in donatable_items(db, player_id, economy) if item_id in catalog]
    if not pool and DEFAULT_WISH_ITEM in catalog:
        pool = [DEFAULT_WISH_ITEM]
    if not pool:
        pool = sorted(catalog)[:1]  # 表在但玩家背包里一个能捐的都没有时的兜底
    for index, entry in enumerate(ai_roster()[:AI_WISH_COUNT]):
        item_id = pool[index % len(pool)]
        num = wish_num_limit(item_id)
        db.execute("""INSERT INTO club_wishes
            (club_id,owner_uid,item_id,want_num,donate_num,got_num,limit_num,donate_count,time)
            VALUES (?,?,?,?,0,0,?,0,?)""",
            (club_id, entry["uid"], item_id, num, num, int(now) + index))


def _settle_due_donations(db, club_id: int, now: float) -> None:
    """把"到点"的人机助力落账 (延迟助力 / 幂等)。

    人机给玩家的助力在落库时写的是**未来时刻** (now+60/90/120s), 未到点前 wish 的
    donate_num/got_num/donate_count 保持 0 —— 这样玩家一发祈愿不会立刻收到助力
    (用户口径「助力玩家可以晚一两分钟或者等玩家切页, 不要一发祈愿就好了」)。
    这里按当前时刻把所有已到点的捐赠重算一遍, 玩家切页(重新进祈愿页)时就会陆续看到。

    计数口径 (用户实测「满了直接没掉, 没法领取, 碎片也没到账」):
      * DonateNum  = 已到点捐赠的**总片数** (含已领与未领) —— 客户端用它显示"收到 x/y"
      * GotNum     = **已领取**的片数 (只统计 received=1) —— 客户端靠 DonateNum>GotNum
                     才画出「领取」按钮; 旧实现把 GotNum 也写成"已到点总数", 于是
                     一到点就 DonateNum==GotNum==WantNum, 客户端判为"已满"把整行收掉,
                     玩家既看不到领取入口也永远领不到碎片。
      * DonateCount= 已到点捐赠的条数 (助力人数)
    """
    now_i = int(now)
    for row in db.execute("SELECT id FROM club_wishes WHERE club_id=?", (club_id,)).fetchall():
        wish_id = int(row["id"])
        agg = db.execute(
            "SELECT count(*) AS c, COALESCE(SUM(num),0) AS n, "
            "COALESCE(SUM(CASE WHEN received=1 THEN num ELSE 0 END),0) AS got "
            "FROM club_wish_donations WHERE wish_id=? AND time<=?",
            (wish_id, now_i)).fetchone()
        db.execute("UPDATE club_wishes SET donate_num=?, got_num=?, donate_count=? WHERE id=?",
                   (int(agg["n"]), int(agg["got"]), int(agg["c"]), wish_id))


def recommend_clubs(now: float) -> list[dict[str, Any]]:
    """推荐社团列表 (确定性生成)。本地只有一个真实玩家, 推荐页需要几行数据才不会空。"""
    clubs = []
    for index, entry in enumerate(ai_roster()[:RECOMMEND_COUNT]):
        member_num = entry["level"] % 10 + 5
        # mem_limit 对齐成员数: 与主页面/成员详情页统一成 "N/N" 口径 (见 _club_meta)。
        clubs.append({"id": RECOMMEND_BASE + index, "name": f"{entry['name']}的社团",
                      "desc": "解神者本地社团", "notice": "", "owner": entry["uid"],
                      "time": int(now), "member_num": member_num,
                      "score": 0, "mem_limit": member_num, "apply_level": 1,
                      "auto_level": 1, "icon": 0})
    return clubs


def _pbs_simple(rec: dict[str, Any]) -> dict[str, Any]:
    """推荐行 -> PBS ClubSimpleData (il2cpp: Id/Name/.../MemberNum/...)。

    ``Meta`` 必须带上 (含 clubIconId), 否则推荐列表里每个社团的头像也都是空白
    (客户端走 ClubModule.GetClubMetaValue("clubIconId") 取图)。
    """
    return {"Id": rec["id"], "Name": rec["name"], "Desc": rec["desc"], "Notice": rec["notice"],
            "Owner": rec["owner"], "Time": rec["time"], "Type": CLUB_JOIN_UNLIMITED,
            "Meta": _club_meta(rec["id"], rec["icon"], rec["mem_limit"]),
            "MemberNum": rec["member_num"], "HistoryScore": 0, "TotalScore": rec["score"],
            "CurScore": 0, "WeekScore": 0, "TotalMedal": 0, "RoundMedal": 0}


def _club_meta(club_id: int, icon: int = 0, mem_limit: int = CLUB_MEM_LIMIT,
               damage: dict[int, int] | None = None,
               today_score: int | None = None) -> list[dict[str, Any]]:
    """ClubData.Meta (ValuePair[]) —— 客户端有几处无守卫地读这些键, 必须带上。

    Value 用 pbs.Value 的成员名: Type=1 (ValueType.Integer) / VString / VInt64。
    ``clubIconId`` 是社团头像: 值为 GuildPicture 表的 GuildPictureID。

    ``clubMemLimit`` 是主页面 "成员数/上限" 的分母; 成员详情页写的是 "(在线:X/Y)"
    (分子=在线数, 分母=成员总数), 两页口径天生不同。客户端不能改, 于是把这里的
    上限直接对齐成实际成员数, 让主页面也显示 "N/N", 与详情页一致。

    ``damage`` = {层号: 累计伤害}, 逐层下发 ``clubDamage_{层号}``: 客户端镜域页的 boss
    剩余血量就是「它自己算出的上限 − 这个值」, 没有键时按 0 (满血) 处理。

    ``today_score`` = 社团今日活动积分 (社团页左上角每日宝箱进度); 传 None 时不下发该键
    (推荐列表那种没有真实日积分的场合)。
    """
    meta = [
        {"Name": CLUB_META_GROUP_CHAT_UUID,
         "Value": {"Type": 1, "VString": "", "VInt64": int(club_id)}},
        {"Name": CLUB_META_LEVEL, "Value": {"Type": 1, "VString": "", "VInt64": 1}},
        {"Name": CLUB_META_MEM_LIMIT,
         "Value": {"Type": 1, "VString": "", "VInt64": int(mem_limit)}},
        {"Name": CLUB_META_ICON,
         "Value": {"Type": 1, "VString": "", "VInt64": int(icon) or DEFAULT_CLUB_ICON}},
    ]
    if today_score is not None:
        meta.append({"Name": CLUB_META_TODAY_SCORE,
                     "Value": {"Type": 1, "VString": "", "VInt64": int(today_score)}})
    for layer in sorted(damage or {}):
        value = int((damage or {}).get(layer) or 0)
        if value > 0:
            meta.append({"Name": f"{CLUB_META_DAMAGE}{int(layer)}",
                         "Value": {"Type": 1, "VString": "", "VInt64": value}})
    return meta


def _tcp_simple(rec: dict[str, Any]) -> dict[str, Any]:
    """推荐行 -> TCP SimpleClubData (commandx2_messages.json 的字段序)。"""
    return {"clubId": rec["id"], "name": rec["name"], "desc": rec["desc"],
            "memNum": rec["member_num"], "memLimit": rec["mem_limit"], "score": rec["score"],
            "autoLevel": rec["auto_level"], "applyLevel": rec["apply_level"], "icon": rec["icon"]}


def _int_list(text: str) -> list[int]:
    out = []
    for part in (text or "").split(","):
        part = part.strip()
        if part:
            try:
                out.append(int(part))
            except ValueError:
                pass
    return out


def _battle_damage(args: dict[str, Any]) -> int:
    """从 PostClubBattle 请求里取玩家打出的伤害。

    PostClubBattleArgs (il2cpp-types.h) 没有专用伤害字段, 只有 Defence/Offensive 两个
    ClubBattleResult{Id,Dstid,Time,Result,Medal}; 这里按优先级取 damage / defence_max_result /
    DefenceMaxResult, 都没有时退回默认基准。**这是推断**, 需按真实抓包复核。
    """
    if isinstance(args, dict):
        for key in ("damage", "Damage"):
            try:
                if key in args:
                    return max(0, int(args[key]))
            except (TypeError, ValueError):
                pass
        for key in ("defence_max_result", "DefenceMaxResult", "defenceMaxResult"):
            try:
                if key in args:
                    return max(0, int(args[key]))
            except (TypeError, ValueError):
                pass
    return DEFAULT_MIRROR_DAMAGE


def _battle_layer(args: dict[str, Any]) -> int:
    """从 PostClubBattle 请求里取打的哪一层 (层 bossId)。

    客户端请求字段未反出, 按常见命名依次尝试; 取不到记 0 (只影响
    «已通关层» 列表, 不影响伤害与次数)。
    """
    if isinstance(args, dict):
        for key in ("bossId", "BossId", "layerId", "LayerId", "sectionId", "SectionId"):
            try:
                if key in args:
                    return int(args[key])
            except (TypeError, ValueError):
                pass
    return 0


_CATALOG_CACHE: dict[int, dict] | None = None


def mirror_catalog() -> dict[int, dict]:
    """镜域试炼关卡目录: {bossId: {winReward, challengeReward, ...}}。

    读 data/club_catalog.json 的 mirror 段 (官方 GuildChallengeInfo 复原);
    读取失败时降级为空表, 调用方用 FIRST_CLEAR_GIFT 兜底。
    """
    global _CATALOG_CACHE
    if _CATALOG_CACHE is None:
        path = Path(__file__).resolve().parent.parent / "data" / "club_catalog.json"
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            _CATALOG_CACHE = {int(row["bossId"]): row for row in (doc.get("mirror") or [])}
        except (OSError, ValueError, KeyError, TypeError):
            _CATALOG_CACHE = {}
    return _CATALOG_CACHE


def mirror_count(db, player_id: int, now: float) -> int:
    """镜域试炼剩余挑战次数: 跨日 +3、上限 5; 顺带把每日集体宝箱标记翻页。

    新档初值就是满的 ``MIRROR_MAX_COUNT`` (用户口径「没打就该是满次数」)。旧代码把初值
    写成 ``MIRROR_DAILY_REGEN``(3), 于是没打过也显示 3/5; 这里再补一条自愈: 当天一次都
    没挑战过 (``battled_count == 0``) 而次数又不满, 说明是那批遗留初值, 直接补满。

    ``club_activity`` 的行往往先被别处以 ``INSERT OR IGNORE (player_id,club_id)`` 建出来,
    此时 ``challege_count``/``regen_day`` 都还是列默认值 0 —— 那不是「昨天打完了」而是
    「从没结算过」。所以 ``regen_day <= 0`` 一律按全新档补满, 否则会走错 +3 分支
    (全新档被算成 3/5, 与「没打就满次数」的口径冲突)。
    调用方负责加锁 / 事务 (ClubReader 用自己的连接, ClubService 用 economy.transaction)。
    """
    today = day_index(int(now))
    row = db.execute(
        "SELECT challege_count, regen_day, battled_count FROM club_activity WHERE player_id=?",
        (player_id,)).fetchone()
    if row is None:
        db.execute("INSERT OR IGNORE INTO club_activity (player_id, challege_count, regen_day) "
                   "VALUES (?,?,?)", (player_id, MIRROR_MAX_COUNT, today))
        return MIRROR_MAX_COUNT
    count, regen_day, battled = int(row[0]), int(row[1]), int(row[2])
    if regen_day != today:
        # regen_day<=0 = 从没跨过日 (全新行, 只被 INSERT OR IGNORE 建过): 直接满次数。
        count = (MIRROR_MAX_COUNT if regen_day <= 0
                 else min(MIRROR_MAX_COUNT, count + MIRROR_DAILY_REGEN))
        db.execute("""UPDATE club_activity SET challege_count=?, regen_day=?, score_reward_flag=0,
            battled_count=0 WHERE player_id=?""", (count, today, player_id))
    elif battled == 0 and count < MIRROR_MAX_COUNT:
        count = MIRROR_MAX_COUNT
        db.execute("UPDATE club_activity SET challege_count=? WHERE player_id=?",
                   (count, player_id))
    return count


def mirror_layer(section: int) -> tuple[int, dict[str, Any]]:
    """镜域关卡的 section id (2170xxx) -> (层号, 目录行)。层号是 1 基 (按 bossId 升序)。"""
    catalog = mirror_catalog()
    for index, boss_id in enumerate(sorted(catalog)):
        row = catalog[boss_id]
        if section in (row.get("stageIds") or []) or section == int(row.get("bossId") or 0):
            return index + 1, row
    return 0, {}


def club_today_score(db, club_id: int, now: float) -> int:
    """社团今日活动积分 (本地日口径): 跨日后读作 0 (惰性归零)。

    客户端社团页左上角每日宝箱进度读的就是这个值 (Meta["clubTodayScore"]), 分母
    300000 = GuildLevel.Level1.DailyScore。
    """
    row = db.execute("SELECT day_score, day_score_day FROM clubs WHERE id=?",
                     (club_id,)).fetchone()
    if row is None or int(row[1]) != day_index(int(now)):
        return 0
    return int(row[0])


def _add_club_day_score(db, club_id: int, points: int, now: float) -> None:
    """给社团今日活动积分加分; 跨日时从 0 重新计 (day_score_day 翻页)。"""
    if int(points) <= 0:
        return
    today = day_index(int(now))
    row = db.execute("SELECT day_score_day FROM clubs WHERE id=?", (club_id,)).fetchone()
    if row is None or int(row[0]) != today:
        db.execute("UPDATE clubs SET day_score=?, day_score_day=? WHERE id=?",
                   (int(points), today, club_id))
    else:
        db.execute("UPDATE clubs SET day_score=day_score+? WHERE id=?", (int(points), club_id))


def _add_member_activity(db, club_id: int, uid: str, damage: int) -> int:
    """把一次镜域伤害累加进成员的伤害榜与积分榜, 返回本次折算出的活动积分。

    ``club_members.damage`` = 镜域累计伤害 (成员成绩榜); ``week_score``/``history_score``
    = 本周/历史活动积分 —— 客户端团内排行的「活动积分」读的就是 WeekScore (弹窗脚注
    「依据本周积分排名, 刷新时间为每周一4:59」)。以前这两列从没被写过, 于是全团积分恒 0
    (用户实测图二)。
    """
    points = max(0, int(damage)) // MIRROR_SCORE_DIV
    row = db.execute("SELECT damage FROM club_members WHERE club_id=? AND uid=?",
                     (club_id, uid)).fetchone()
    total = (int(row[0]) if row is not None else 0) + int(damage)
    db.execute("""UPDATE club_members SET damage=?, week_score=week_score+?,
        history_score=history_score+? WHERE club_id=? AND uid=?""",
        (total, points, points, club_id, uid))
    return points


def ai_battle_damage(base: int = 0) -> int:
    """人机**单次**镜域挑战打出的伤害 = 玩家本局真实伤害 × [120%, 150%] 随机。

    ``base`` = 玩家本局**真实伤害** (887 上报); 拿不到时退回 ``MIRROR_DAMAGE_PER_RUN``
    估算 (没有真实值的旧路径 / 旧存档重放)。
    """
    unit = int(base) if int(base or 0) > 0 else MIRROR_DAMAGE_PER_RUN
    return int(unit * random.uniform(MIRROR_AI_RATIO_MIN, MIRROR_AI_RATIO_MAX))


def _settle_ai_battles(db, club_id: int, now: float, base: int = 0) -> int:
    """玩家打完一次后, 全体人机各**跟打 1 次**, 每人**各自独立**掷 120%~150%。

    每个成员的单次伤害单独随机 (不是"算一个值发给所有人"), 否则 21 个成员的积分榜会排成
    一条直线 (用户实测「现在全都是一样的」)。成绩**累加**进每个成员 (伤害榜 + 活动积分榜),
    并同步进社团今日活动积分。**不扣 boss 血**: 人机单次就是玩家的 1.5 倍, 21 个人机一局
    就顶玩家 30 局, 也进血池会让血条一局清空 (用户要求 boss 能打好几天)。返回合计伤害。
    """
    total = 0
    points = 0
    for entry in club_roster():
        damage = ai_battle_damage(base)
        total += damage
        points += _add_member_activity(db, club_id, entry["uid"], damage)
    _add_club_day_score(db, club_id, points, now)
    return total


def settle_mirror_checkout(db, economy, player_id: int, section: int, success: bool,
                           damage: int, now: float) -> dict[str, Any]:
    """镜域试炼结算 (事件循环侧, 与 BattleService.checkout 同一事务)。

    客户端打完镜域**不发** PostClubBattle / ClubReceiveReward (抓包 2026-10-12 全程没有),
    所以挑战次数、伤害、公会血池、奖励全部在这里按本次结算自行推导:
    * 无论胜负都消耗一次挑战次数, 并把该层记进 battled_sections;
    * 通关给该层等值奖励 (club_catalog.mirror[*].winReward), 该层**首通**另加尘封宝箱
      (challengeReward = 778201), 使结算页的「获得奖励」不再为空;
    * 玩家本次**真实伤害** (``damage``, 来自 887 antiCheat / hp) 累加进公会血池
      (club_activity.mirror_damage), 由 _club_meta 以 clubDamage_{层号} 下发, 客户端
      据此扣 boss 血条; 同时折算成活动积分写进成员榜与社团今日积分 (每日宝箱进度);
    * 人机在玩家打完一局后各**跟打 1 次** (每人 = 玩家本局真实伤害 × 120%~150%): 只写
      成员成绩榜 (club_members.damage / week_score), **不进 boss 血池** —— 21 个人机一局
      就顶玩家 30 局, 若也扣 boss 血条会一局清空 (用户要求 boss 能打好几天)。

    返回 {"rewardData": bytes, "layer": int, "damage": int}。
    """
    club_id = ensure_membership(db, player_id, now)
    db.execute("INSERT OR IGNORE INTO club_activity (player_id,club_id) VALUES (?,?)",
               (player_id, club_id))
    count = mirror_count(db, player_id, now)
    layer, entry = mirror_layer(section)
    # 真实伤害照单全收: 只要打的是镜域某层, 客户端上报多少就记多少 (real damage)。
    damage = max(0, int(damage or 0)) if layer else 0
    row = db.execute("SELECT received_layer, battled_sections, mirror_damage FROM club_activity "
                     "WHERE player_id=?", (player_id,)).fetchone()
    sections = _int_list(row["battled_sections"]) if row is not None else []
    if section and section not in sections:
        sections.append(section)
    pool = _damage_map(row["mirror_damage"]) if row is not None else {}
    if damage and layer:
        pool[layer] = pool.get(layer, 0) + damage
    # 人机成绩也结算到成员榜 (base = 玩家本局真实伤害), 但**不写进 boss 血池** (见上)。
    _settle_ai_battles(db, club_id, now, base=damage)
    db.execute("""UPDATE club_activity SET challege_count=?, battled_count=battled_count+1,
        battled_sections=?, mirror_damage=? WHERE player_id=?""",
        (max(0, count - 1), ",".join(str(v) for v in sections), _damage_text(pool), player_id))
    if damage:
        _add_club_day_score(db, club_id,
                            _add_member_activity(db, club_id, player_uid(player_id), damage), now)
    rewards: dict[int, int] = {}
    if success and entry:
        gifts = []
        win = int(entry.get("winReward") or 0)
        if win:
            gifts.append(win)
        # 首通该层: 另给尘封宝箱。received_layer 存的是 bossId (与 _ClubReceiveReward 同口径)。
        received = _int_list(row["received_layer"]) if row is not None else []
        boss_id = int(entry.get("bossId") or 0)
        if boss_id and boss_id not in received:
            gifts.append(int(entry.get("challengeReward") or FIRST_CLEAR_GIFT))
            received.append(boss_id)
            db.execute("UPDATE club_activity SET received_layer=? WHERE player_id=?",
                       (",".join(str(v) for v in received), player_id))
        if gifts:
            rewards = economy.gifts(gifts)
            economy._grant(player_id, f"club:mirror:{player_id}:{section}:{int(now)}", rewards)
    return {"rewardData": economy.reward_bytes_visible(rewards, []),
            "layer": layer, "damage": damage}


# ---- PBS 读取端 -----------------------------------------------------------

class ClubReader:
    """社团 PBS 路由的读取端。HTTP worker 线程服务, 自带一条 SQLite 连接。"""

    def __init__(self, path, economy=None) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=10)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        # economy 只用于读 self.items / STACKABLE_REWARD_TYPES 挑祈愿道具 (只读, 跨线程安全)。
        self.economy = economy
        ensure_club_schema(self.db)
        self.db.commit()

    def close(self) -> None:
        with self._lock:
            self.db.close()

    # ---- 内部工具 -------------------------------------------------------

    def _snapshot(self, player_id: int) -> dict[str, Any]:
        row = self.db.execute("SELECT snapshot FROM players WHERE id=?", (player_id,)).fetchone()
        if row is None:
            return {}
        import json
        try:
            return json.loads(row["snapshot"])
        except (TypeError, ValueError):
            return {}

    def _member_attrib(self, uid: str) -> dict[str, Any]:
        entry = roster_entry(uid)
        if entry is not None:
            return _attrib(uid, entry["name"], entry["head"], entry["level"])
        try:
            player_id = int(uid)
        except (TypeError, ValueError):
            return _attrib(uid, "解神者", 1000001, 1)
        snap = self._snapshot(player_id)
        return _attrib(uid, snap.get("nickname", "解神者"), snap.get("head_icon", 1000001),
                       int(snap.get("level", 1)))

    def _join_default(self, player_id: int, now: float) -> int:
        with self._lock, self.db:
            return ensure_membership(self.db, player_id, now)

    def _mirror_damage(self, player_id: int) -> dict[int, int]:
        """该玩家的公会镜域血池 {层号: 累计伤害} (Meta 下发 clubDamage_{层号} 用)。"""
        row = self.db.execute("SELECT mirror_damage FROM club_activity WHERE player_id=?",
                              (player_id,)).fetchone()
        return _damage_map(row["mirror_damage"]) if row is not None else {}

    def _member_dict(self, row, now: float) -> dict[str, Any]:
        uid, damage = str(row["uid"]), int(row["damage"])
        # 镜域试炼伤害 (P4): 挂在 Actives (ClubActiveEvent {Event,Time,Score}) 里, Score 也带上。
        actives = [{"Event": 0, "Time": int(row["time"]), "Score": damage}] if damage else []
        # Userid 给对外的**数字** uid (ai1003 -> 1003): 客户端拿字符串全等查
        # ClubMember.Userid (ClubModule_GetMemberByUserID), 也拿 Int64.TryParse 解析
        # 祈愿行的 Userid, 非数字会被整行丢弃 (见 club_uid)。
        return {"Userid": club_uid(uid), "Post": int(row["post"]), "Time": int(row["time"]),
                "Actives": actives, "Score": damage, "WeekScore": int(row["week_score"]),
                "HistoryScore": int(row["history_score"]), "Medal": int(row["medal"]),
                "RoundMedal": int(row["round_medal"]), "WinNum": 0, "WinTime": 0,
                "Attrib": self._member_attrib(uid), "IsOnline": True}

    def _simple_of(self, club, member_num: int, now: float,
                   damage: dict[int, int] | None = None,
                   today_score: int = 0) -> dict[str, Any]:
        return {"Id": int(club["id"]), "Name": club["name"], "Desc": club["desc"],
                "Notice": club["notice"], "Owner": club["owner"], "Time": int(club["create_time"]),
                "Type": int(club["type"]),
                "Meta": _club_meta(int(club["id"]), int(club["icon"]), int(member_num), damage,
                                   today_score),
                "MemberNum": int(member_num),
                "HistoryScore": int(club["history_score"]), "TotalScore": int(club["total_score"]),
                "CurScore": int(club["cur_score"]), "WeekScore": int(club["week_score"]),
                "TotalMedal": int(club["total_medal"]), "RoundMedal": int(club["round_medal"])}

    # ---- 报文构造 -------------------------------------------------------

    def club_data(self, player_id: int, now: float) -> dict[str, Any]:
        club_id = self._join_default(player_id, now)
        with self._lock:
            club = self.db.execute("SELECT * FROM clubs WHERE id=?", (club_id,)).fetchone()
            members = self.db.execute(
                "SELECT * FROM club_members WHERE club_id=? ORDER BY post DESC, time, uid",
                (club_id,)).fetchall()
            damage = self._mirror_damage(player_id)
            today_score = club_today_score(self.db, club_id, now)
        if club is None:
            return {}
        return {"Id": int(club["id"]), "Name": club["name"], "Desc": club["desc"],
                "Notice": club["notice"], "Owner": club["owner"], "Time": int(club["create_time"]),
                "Type": int(club["type"]),
                "Meta": _club_meta(int(club["id"]), int(club["icon"]), len(members), damage,
                                   today_score),
                "MemberList": [self._member_dict(row, now) for row in members],
                "ApplyList": [], "EventList": [], "HistoryScore": int(club["history_score"]),
                "TotalScore": int(club["total_score"]), "CurScore": int(club["cur_score"]),
                "WeekScore": int(club["week_score"]), "ResetWeekTime": int(club["reset_week_time"]),
                "TotalMedal": int(club["total_medal"]), "RoundMedal": int(club["round_medal"])}

    def club_simple(self, player_id: int, now: float) -> dict[str, Any]:
        club_id = self._join_default(player_id, now)
        with self._lock:
            club = self.db.execute("SELECT * FROM clubs WHERE id=?", (club_id,)).fetchone()
            count = self.db.execute("SELECT count(*) FROM club_members WHERE club_id=?",
                                    (club_id,)).fetchone()[0]
            damage = self._mirror_damage(player_id)
            today_score = club_today_score(self.db, club_id, now)
        return (self._simple_of(club, count, now, damage, today_score)
                if club is not None else {})

    def recommend_simple(self, now: float) -> list[dict[str, Any]]:
        return [_pbs_simple(rec) for rec in recommend_clubs(now)]

    def wishing_page(self, player_id: int, now: float) -> dict[str, Any]:
        club_id = self._join_default(player_id, now)
        with self._lock, self.db:
            ensure_ai_wishes(self.db, club_id, player_id, self.economy, now)
            # 延迟助力: 把已到点的人机捐赠落进 wish 计数 (玩家切页/重进时触发)。
            _settle_due_donations(self.db, club_id, now)
        with self._lock:
            rows = self.db.execute("SELECT * FROM club_wishes WHERE club_id=? ORDER BY time, id",
                                   (club_id,)).fetchall()
            wishes = []
            for row in rows:
                # 只列**已到点**的助力 (time<=now); 未来时刻的是"还在路上"的人机。
                donors = self.db.execute(
                    "SELECT donor_uid,num,time FROM club_wish_donations "
                    "WHERE wish_id=? AND time<=? ORDER BY id",
                    (row["id"], int(now))).fetchall()
                wishes.append({"Wid": int(row["id"]), "Userid": club_uid(row["owner_uid"]),
                    "ItemId": int(row["item_id"]), "Time": int(row["time"]),
                    "WantNum": int(row["want_num"]), "DonateNum": int(row["donate_num"]),
                    "GotNum": int(row["got_num"]), "LimitNum": int(row["limit_num"]),
                    "DonateCount": int(row["donate_count"]),
                    "Donors": [{"Userid": club_uid(d["donor_uid"]), "Num": int(d["num"]),
                                "Time": int(d["time"])} for d in donors], "Exp": 0})
        return {"Total": len(wishes), "List": wishes}

    def wishing_history(self, player_id: int, now: float) -> dict[str, Any]:
        with self._lock:
            rows = self.db.execute("""SELECT w.id,w.owner_uid,d.donor_uid,w.item_id,d.num,d.time
                FROM club_wish_donations d JOIN club_wishes w ON w.id=d.wish_id
                WHERE w.club_id=? AND d.time<=? ORDER BY d.time, d.id""",
                (club_id_of(self.db, player_id), int(now))).fetchall()
        # 时间标度: 客户端渲染「受赠/赠送记录」的时间时是
        #   span = GetServerTime() - (Time - to2018)      (ClubWishHistory_WishHistoryNode_Refresh)
        # 其中 to2018 = 1514736000 是客户端写死的常量。所以下发的 Time 必须**加上** to2018,
        # 否则 span 恒等于 to2018 -> 每条记录都显示「17532天前」(用户实测图一/图二)。
        items = [{"Wid": int(r["id"]), "Userid": club_uid(r["owner_uid"]),
                  "Donor": club_uid(r["donor_uid"]),
                  "ItemId": int(r["item_id"]), "ItemNum": int(r["num"]),
                  "Time": int(r["time"]) + _TO_2018}
                 for r in rows]
        return {"Total": len(items), "Items": items}

    def kvs_values(self, users: list, keys: list, now: float) -> list[dict[str, Any]]:
        """KVStoreService.GetValuesV2 的 ``club_speed_*`` 读取端 (公会助力页的建筑列表)。

        回包必须**按 userid 分组** —— GetValuesV2Reply.Pairs 是 KeyValuePairs[]
        ({Userid, Pairs:[KeyValuePair{Key,Val}]}); 客户端 GetAllBuildHelpInfo 逐
        KeyValuePairs 取 Userid 作行主键, 再逐内层 Val 反序列化成
        HelpedBuildingData{buildId,upgradeEndTime,buildLevel}。因为键名里已经带了 uid,
        这里就按键里的 uid 分组 (不是 users×keys 的笛卡尔积), 每条键只回一份, 避免
        客户端把同一个成员的行按"每个 user"重复加进列表。

        只发**人机**成员: 客户端对 ``Userid == 本人`` 的节点显示「求助」按钮, 而那条
        链路走社团聊天服务 (ChatModule_SendClubChat -> ChatService.PublishMsgAsync,
        TCP 打到 29001 的聊天节点), 本服不监听 -> 发出来就是个点了没反应的死按钮。
        玩家自己造什么、剩多久由 584/579 下发, 不需要在这里重复。
        """
        grouped: dict[str, list[int]] = {}
        for key in keys:
            parsed = parse_help_key(key)
            if parsed is None:
                continue
            uid, slot = parsed
            grouped.setdefault(uid, []).append(slot)
        if not grouped:
            return []
        reply = []
        for uid, slots in grouped.items():
            # 人机 uid 能在名册里查到; 玩家自己的 uid (十进制串) 查不到 -> 跳过。
            if roster_entry(db_uid(uid)) is None:
                continue
            pairs = [{"key": f"{CLUB_HELP_KEY}{uid}_{slot}",
                      "val": json.dumps(help_building_value(uid, slot, now),
                                        separators=(",", ":"))}
                     for slot in sorted(set(slots))]
            if pairs:
                reply.append({"userid": uid, "pairs": pairs})
        return reply

    def club_member(self, args: dict[str, Any], now: float) -> dict[str, Any]:
        """GetClubMember (PBS): 按成员 uid 取一条 ClubMember (getId + Member)。

        请求里的 member 是对外的数字 uid ("1003"), 这里反查回库内的人机 uid ("ai1003")。
        """
        uid = db_uid(args.get("member") or args.get("Member") or "")
        with self._lock:
            row = self.db.execute("SELECT * FROM club_members WHERE uid=?", (uid,)).fetchone()
        if row is None:
            return {"Id": 0, "Member": {}}
        return {"Id": int(row["club_id"]), "Member": self._member_dict(row, now)}

    def record_battle(self, player_id: int, args: dict[str, Any], now: float) -> dict[str, Any]:
        """PostClubBattle (PBS): 扣一次镜域挑战次数, 记录伤害/已打层。

        **不发奖** —— 这里跑在 HTTP worker 线程, 持有自己的 SQLite 连接, 跨线程调
        economy._grant 会踩事件循环的 store.db。奖励由后续 TCP 的 C2L_ClubReceiveReward
        领取 (见 ClubService._ClubReceiveReward)。
        """
        result = {"CheckFailIdx": 0, "IsMainDefence": False, "IsMainOffensive": False,
                  "ClubTotalMedal": 0, "ClubRoundMedal": 0, "UserTotalMedal": 0,
                  "IsAdvance": False, "GotMedal": 0}
        club_id = self._join_default(player_id, now)
        damage = _battle_damage(args)
        with self._lock, self.db:
            self.db.execute("INSERT OR IGNORE INTO club_activity (player_id,club_id) VALUES (?,?)",
                            (player_id, club_id))
            if mirror_count(self.db, player_id, now) <= 0:
                # 次数用完: 不算这一场的伤害/层, 也不扣次数 (客户端按 challegeCount 显示)。
                return result
            layer = _battle_layer(args)
            row = self.db.execute(
                "SELECT battled_sections, mirror_damage FROM club_activity WHERE player_id=?",
                (player_id,)).fetchone()
            sections = _int_list(row["battled_sections"]) if row is not None else []
            if layer and layer not in sections:
                sections.append(layer)
            pool = _damage_map(row["mirror_damage"]) if row is not None else {}
            if layer:
                pool[layer] = pool.get(layer, 0) + damage
            self.db.execute("""UPDATE club_activity SET club_id=?, challege_count=challege_count-1,
                battled_count=battled_count+1, damage=?, battled_sections=?, mirror_damage=?
                WHERE player_id=?""",
                (club_id, damage, ",".join(str(v) for v in sections), _damage_text(pool), player_id))
            _add_club_day_score(self.db, club_id,
                                _add_member_activity(self.db, club_id,
                                                     player_uid(player_id), damage), now)
            # 人机在玩家打完之后各跟打 1 次: 只进成员成绩榜与积分榜, 不进 boss 血池
            # (理由见 settle_mirror_checkout)。
            _settle_ai_battles(self.db, club_id, now, base=damage)
        return result

    def rank_query(self, now: float) -> dict[str, Any]:
        """``/RankingService.QueryRank``: 社团排行页 (ClubModule_GetClubRankList)。

        字段形状来自客户端自己的 DTO (work/cpp/appdata/il2cpp-types.h 的
        ``Response_1_QueryRankReply_`` / ``QueryRankReply`` / ``RankItem``):
        Total/TotalPage/Members(RankItem[])/MemberRank/MemberScore/MemberMetadata。
        这条路由以前完全没实现 -> 日志里客户端 POST 它拿到 404, 而本服会**把非 200 弹成
        提示框**。这里按离线参考 x2e_ref/src/server/pbs_replies.inc 的口径回一份**合法但
        为空**的答复 (Members=[]), 不再弹提示: 跨团排行是全局榜, 单机名册里只有本团一个
        社团, 没有可排的其它团, 编造行反而可能让客户端解析出错误内容。
        """
        return {"Total": 0, "TotalPage": 0, "Members": [],
                "MemberRank": 0, "MemberScore": 0, "MemberMetadata": ""}

    # ---- 路由分发 -------------------------------------------------------

    def handle(self, path: str, args: dict[str, Any], player_id: int,
               now: float) -> dict[str, Any]:
        """按路由返回 Data (外层信封由 local_identity 统一加)。"""
        if path == "/ClubService.GetClub":
            return {"Club": self.club_data(player_id, now)}
        if path in ("/ClubService.QueryClub", "/ClubService.FilterClub"):
            return {"Total": RECOMMEND_COUNT, "Pages": self.recommend_simple(now)}
        if path == "/ClubService.GetClubSimple":
            return {"Club": self.club_simple(player_id, now)}
        if path == "/ClubService.GetClubSimpleV2":
            return {"Clubs": [self.club_simple(player_id, now), *self.recommend_simple(now)]}
        if path == "/ClubService.FetchClubSimple":
            return {"ClubList": self.recommend_simple(now)}
        if path == "/ClubService.GetClubMember":
            # 请求参数 = GetClubMemberArgs{Appid, Member} (成员 uid, 可能是 "aiXXXX")。
            return self.club_member(args, now)
        if path == "/ClubService.GetWishingPage":
            return self.wishing_page(player_id, now)
        if path == "/ClubService.QueryWishingHistory":
            return self.wishing_history(player_id, now)
        if path == "/ClubService.PostClubBattle":
            return self.record_battle(player_id, args, now)
        return {}


# ---- TCP 操作端 -----------------------------------------------------------

class ClubService:
    """社团写/操作类 TCP handler (照 mail.MailService 的 handle 模式)。"""

    def __init__(self, store, economy, clock=time.time) -> None:
        self.store, self.economy, self.clock = store, economy, clock
        # 祈愿助力/领奖会改背包 (金币/学级积分/碎片), 而右上角的学级积分只在
        # PlayerDataProto 里 (login.snapshot_push 从背包回填 GuildScore)。构造器由
        # run_server.py 注入 LoginService.snapshot_push; 未接线时下面的 push 都返回空。
        self.snapshot_push = None
        with store.db:
            ensure_club_schema(store.db)

    def _item_push(self, player_id: int):
        """背包变动 (金币/学级积分/碎片) 的 L2C_ItemUpdate 补推 (照 social.py 同款)。"""
        if self.economy is None:
            return ()
        return (OutboundMessage("L2C_ItemUpdate",
                                {"code": 10, **self.economy.inventory_values(player_id)}),)

    def _refresh_pushes(self, player_id: int):
        """整份 PlayerDataProto 补推, 放在响应帧**之前**。

        客户端收 767/769 回包后会立刻读 PlayerData.BaseInfo.GuildScore 刷新右上角学级
        积分; GuildScore 只在 snapshot_push 时从背包回填 (见 login.py), 所以这里必须重推
        一份, 否则背包加了分而 HUD 停在旧值 —— 用户实测的"横幅出现但右上角一直是 0"。
        """
        if self.snapshot_push is None or self.store is None:
            return ()
        from .login import LoginService
        fresh = self.store.get(player_id)
        return (self.snapshot_push(
            fresh,
            self.store.inventory_quantities(player_id, LoginService.profile_currency_items()),
            store=self.store),)

    def handlers(self):
        return {"C2L_" + name: self.handle for name in (
            "CreateClub", "RecommandClub", "AppalyJoinClub", "QuickJoinClub", "UpdateClubInfo",
            "UpdateClubRecruit", "JoinClubListner", "ClubApproval", "UpdateMemberPrivilege",
            "DismissMember", "QuitClub", "ClubActiMainData", "ClubWishing", "ClubWishingCount",
            "ClubWishingDonate", "ClubWishingReceive", "ClubReceiveReward")}

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("club request before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = CLUB_SCHEMAS[name].decode(packet.body)
        now = self.clock()
        return self._dispatch[name](self, player_id, req, now)

    def _club_id(self, player_id: int, now: float) -> int:
        with self.economy.transaction():
            return ensure_membership(self.store.db, player_id, now)

    def _is_chip(self, item_id: int) -> bool:
        """是不是神格碎片 (ItemType E_Chip=12)。"""
        info = self.economy.items.get(item_id) or {}
        return info.get("ItemType", {}).get("value") == CHIP_ITEM_TYPE

    def _owns_item(self, player_id: int, item_id: int) -> bool:
        """背包里有没有这个道具 (数量 > 0)。"""
        row = self.store.db.execute(
            "SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
            (player_id, item_id)).fetchone()
        return row is not None and int(row[0]) > 0

    def _level_of(self, player_id: int) -> int:
        return int(self.store.get(player_id)["snapshot"].get("level", 1))

    def _below_open_level(self, player_id: int) -> bool:
        """社团 17 级解锁 (客户端 FunctionOpen 也在拦, 这里只兜底写接口)。"""
        return self._level_of(player_id) < CLUB_OPEN_LEVEL

    def _add_club_score(self, club_id: int, player_id: int, points: int) -> None:
        self.store.db.execute("""UPDATE clubs SET cur_score=cur_score+?, total_score=total_score+?,
            week_score=week_score+? WHERE id=?""", (points, points, points, club_id))
        self.store.db.execute("UPDATE club_members SET score=score+? WHERE club_id=? AND uid=?",
                              (points, club_id, player_uid(player_id)))

    def _add_member_score(self, club_id: int, uid: str, points: int) -> None:
        """只给某个成员 (按库内 uid) 记学级积分, 不动社团总分。

        祈愿助力是"双方都得分": 捐赠方走 ``_add_club_score`` (含社团总分), 被助力的
        祈愿主人若是人机, 就只在他自己的成员行上加一份 (人机不持有学级积分道具)。
        """
        self.store.db.execute("UPDATE club_members SET score=score+? WHERE club_id=? AND uid=?",
                              (points, club_id, uid))

    # ---- C2L 各消息 -----------------------------------------------------

    def _CreateClub(self, player_id: int, req: dict[str, Any], now: float):
        club_id = self._club_id(player_id, now)
        if self._below_open_level(player_id):
            return OutboundMessage("L2C_CreateClub",
                                   {"code": CODE_REFUSED, "clubId": club_id, "opt": 0})
        name = (req.get("name") or "").strip() or DEFAULT_CLUB_NAME
        with self.economy.transaction():
            # 建团消耗少量金币 (攻略); 官方表无费用字段, 数值见 CREATE_CLUB_COST。
            snapshot = self.store.get(player_id)["snapshot"]
            try:
                self.economy._spend(player_id, snapshot, GOLD_ITEM, CREATE_CLUB_COST)
            except UnresolvedEconomy:
                return OutboundMessage("L2C_CreateClub",
                                       {"code": CODE_REFUSED, "clubId": club_id, "opt": 0})
            self.economy._write_snapshot(player_id, snapshot)
            self.store.db.execute("UPDATE clubs SET name=?, desc=?, icon=? WHERE id=?",
                (name, req.get("desc") or "",
                 int(req.get("clubIconId") or 0) or DEFAULT_CLUB_ICON, club_id))
        return OutboundMessage("L2C_CreateClub", {"code": CODE_OK, "clubId": club_id, "opt": 0})

    def _RecommandClub(self, player_id: int, req: dict[str, Any], now: float):
        simple = [SIMPLE_CLUB_DATA.encode(_tcp_simple(rec)) for rec in recommend_clubs(now)]
        return OutboundMessage("L2C_RecommandClub",
                               {"code": CODE_OK, "simpleClubData": simple, "pageTotal": 1})

    def _AppalyJoinClub(self, player_id: int, req: dict[str, Any], now: float):
        club_id = req.get("clubId", 0)
        if self._below_open_level(player_id):
            return OutboundMessage("L2C_AppalyJoinClub",
                                   {"code": CODE_REFUSED, "result": 0, "clubId": club_id})
        with self.economy.transaction():
            club_id = join_club(self.store.db, player_id, club_id, now)
        return OutboundMessage("L2C_AppalyJoinClub",
                               {"code": CODE_OK, "result": 0, "clubId": club_id})

    def _QuickJoinClub(self, player_id: int, req: dict[str, Any], now: float):
        ids = [int(v) for v in (req.get("clubIds") or [])]
        club_id = ids[0] if ids else recommend_clubs(now)[0]["id"]
        if self._below_open_level(player_id):
            return OutboundMessage("L2C_QuickJoinClub",
                                   {"code": CODE_REFUSED, "result": 0, "clubId": club_id})
        with self.economy.transaction():
            club_id = join_club(self.store.db, player_id, club_id, now)
        return OutboundMessage("L2C_QuickJoinClub",
                               {"code": CODE_OK, "result": 0, "clubId": club_id})

    def _UpdateClubInfo(self, player_id: int, req: dict[str, Any], now: float):
        club_id = self._club_id(player_id, now)
        with self.economy.transaction():
            self.store.db.execute("UPDATE clubs SET name=?, icon=?, notice=? WHERE id=?",
                (req.get("name") or DEFAULT_CLUB_NAME,
                 int(req.get("clubIconId") or 0) or DEFAULT_CLUB_ICON,
                 req.get("notice") or "", club_id))
        return OutboundMessage("L2C_UpdateClubInfo", {"code": CODE_OK, "opt": req.get("opt", 0)})

    def _UpdateClubRecruit(self, player_id: int, req: dict[str, Any], now: float):
        club_id = self._club_id(player_id, now)
        with self.economy.transaction():
            self.store.db.execute("""UPDATE clubs SET desc=?, apply_level=?, auto_level=?
                WHERE id=?""", (req.get("desc") or "", req.get("applyAbleLevel", 1),
                                req.get("applyAbleAutoLevel", 1), club_id))
        return OutboundMessage("L2C_UpdateClubRecruit", {"code": CODE_OK})

    def _JoinClubListner(self, player_id: int, req: dict[str, Any], now: float):
        return OutboundMessage("L2C_JoinClubListner", {"code": CODE_OK})

    def _ClubApproval(self, player_id: int, req: dict[str, Any], now: float):
        return OutboundMessage("L2C_ClubApproval", {"code": CODE_OK})

    def _UpdateMemberPrivilege(self, player_id: int, req: dict[str, Any], now: float):
        club_id = self._club_id(player_id, now)
        with self.economy.transaction():
            self.store.db.execute("UPDATE club_members SET post=? WHERE club_id=? AND uid=?",
                (req.get("opt", CLUB_POST_MEMBER), club_id, db_uid(req.get("optedId"))))
        return OutboundMessage("L2C_UpdateMemberPrivilege", {"code": CODE_OK})

    def _DismissMember(self, player_id: int, req: dict[str, Any], now: float):
        club_id = self._club_id(player_id, now)
        # 客户端给的是对外数字 uid ("1003"), 反查回库内 "ai1003" 才能删到人。
        uid = db_uid(req.get("optedId"))
        if uid and uid != player_uid(player_id):
            with self.economy.transaction():
                self.store.db.execute("DELETE FROM club_members WHERE club_id=? AND uid=?",
                                      (club_id, uid))
        return OutboundMessage("L2C_DismissMember", {"code": CODE_OK})

    def _QuitClub(self, player_id: int, req: dict[str, Any], now: float):
        with self.economy.transaction():
            self.store.db.execute("DELETE FROM club_members WHERE uid=?",
                                  (player_uid(player_id),))
        return OutboundMessage("L2C_QuitClub",
                               {"postId": req.get("postId", 0), "code": CODE_OK})

    def _ClubActiMainData(self, player_id: int, req: dict[str, Any], now: float):
        with self.economy.transaction():
            club_id = ensure_membership(self.store.db, player_id, now)
            self.store.db.execute("INSERT OR IGNORE INTO club_activity (player_id,club_id) "
                                  "VALUES (?,?)", (player_id, club_id))
            # 顺带结算跨日恢复 (+3, 上限 5) 并把每日集体宝箱标记翻页。
            count = mirror_count(self.store.db, player_id, now)
        row = self.store.db.execute("SELECT * FROM club_activity WHERE player_id=?",
                                    (player_id,)).fetchone()
        return OutboundMessage("L2C_ClubActiMainData", {
            "code": CODE_OK, "challegeCount": count,
            "receivedLayer": _int_list(row["received_layer"]),
            "scoreRewardFlag": int(row["score_reward_flag"]),
            "battledSectionIds": _int_list(row["battled_sections"])})

    def _ClubReceiveReward(self, player_id: int, req: dict[str, Any], now: float):
        """镜域试炼/社团活动的领奖入口 (唯一能安全发奖的 TCP 侧)。

        opt/param 的确切语义客户端未反出 (见实施计划第四节), 按数据落点推断:
        * opt==0 & param=层bossId: 该层**首次**通关 -> 尘封宝箱 (club_catalog.challengeReward,
          各层都是 778201); 重复挑战 -> 该层基础奖励 (club_catalog.winReward, 778101..778140)。
        * opt==1: 每日集体积分达标宝箱 (GuildLevel Lv1 DailyAward = 778202), 每天一次。
        * 其它: 保持旧兜底 (少量金币), 避免客户端点了没反应。
        """
        opt = int(req.get("opt", 0) or 0)
        param = int(req.get("param", 0) or 0)

        def _refused():
            return OutboundMessage("L2C_ClubReceiveReward",
                                   {"code": CODE_REFUSED, "rewardData": b"", "param": param})

        try:
            with self.economy.transaction():
                club_id = ensure_membership(self.store.db, player_id, now)
                self.store.db.execute(
                    "INSERT OR IGNORE INTO club_activity (player_id,club_id) VALUES (?,?)",
                    (player_id, club_id))
                row = self.store.db.execute(
                    "SELECT received_layer, score_reward_flag FROM club_activity WHERE player_id=?",
                    (player_id,)).fetchone()
                received = _int_list(row["received_layer"])
                layer = mirror_catalog().get(param) or {}
                if opt == 1:
                    # 每日集体积分达标宝箱
                    if int(row["score_reward_flag"]):
                        return _refused()
                    rewards = self.economy.gifts([DAILY_SCORE_GIFT])
                    self.economy._grant(player_id, f"club:dailybox:{day_index(int(now))}", rewards)
                    self.store.db.execute(
                        "UPDATE club_activity SET score_reward_flag=1 WHERE player_id=?",
                        (player_id,))
                elif opt == 0 and param > 0 and param not in received:
                    # 该层首次通关: 尘封宝箱
                    gift = int(layer.get("challengeReward") or FIRST_CLEAR_GIFT)
                    rewards = self.economy.gifts([gift])
                    self.economy._grant(player_id, f"club:firstclear:{param}", rewards)
                    received.append(param)
                    self.store.db.execute(
                        "UPDATE club_activity SET received_layer=? WHERE player_id=?",
                        (",".join(str(v) for v in received), player_id))
                elif opt == 0 and param > 0:
                    # 重复挑战: 只给该层基础奖励
                    gift = int(layer.get("winReward") or 0)
                    if not gift:
                        return _refused()
                    rewards = self.economy.gifts([gift])
                    self.economy._grant(
                        player_id, f"club:repeat:{param}:{player_id}:{int(now)}", rewards)
                else:
                    rewards = {GOLD_ITEM: RECEIVE_REWARD_GOLD}
                    self.economy._grant(player_id, f"club:reward:{player_id}:{param}", rewards)
        except UnresolvedEconomy:
            return _refused()
        return OutboundMessage("L2C_ClubReceiveReward", {
            "code": CODE_OK, "rewardData": self.economy.reward_bytes(rewards), "param": param})

    def _ClubWishing(self, player_id: int, req: dict[str, Any], now: float):
        """玩家发布祈愿 -> 人机**延迟**助力 (60/90/120 秒后到账, 或玩家切页时结算)。

        规则 (官方攻略 + GuildWish 表): 同一种道具每日最多发布 NumLimit 次
        (1/2 星 3 次, 3 星 2 次); 发布要花 Consume 里的金币; 只能祈愿**自己已拥有**的
        神格碎片; 每日最多收 want_num(NumLimit) 片。助力不再"一发祈愿就到账" (用户口径),
        落库时写成未来时刻的捐赠记录, 由 ClubReader.wishing_page 的 _settle_due_donations
        到点结算。
        """
        club_id = self._club_id(player_id, now)
        item_id = int(req.get("itemId", 0) or 0)

        def _refused():
            return OutboundMessage("L2C_ClubWishing",
                                   {"code": CODE_REFUSED, "itemId": item_id})

        # 1) 同一种道具每日发布次数上限 (本地日 00:00 翻页)
        start, _ = day_period(int(now))
        made = self.store.db.execute(
            "SELECT count(*) FROM club_wishes WHERE owner_uid=? AND item_id=? AND time>=?",
            (player_uid(player_id), item_id, start)).fetchone()[0]
        if made >= wish_daily_limit(item_id):
            return _refused()
        # 2) 只能祈愿自己已拥有的神格碎片 (非碎片材料不拦, 攻略允许祈愿养成材料)
        if item_id > 0 and self._is_chip(item_id) and not self._owns_item(player_id, item_id):
            return _refused()
        # 3) itemId 必须命中官方 GuildWish 表, 否则客户端查表失败会让整个祈愿页渲染不出来。
        if item_id not in wish_catalog():
            return _refused()
        want = wish_num_limit(item_id)
        cost = wish_consume(item_id)

        with self.economy.transaction():
            # 发布消耗金币 (GuildWish.Consume, 901 = 金币); 不够就整单拒绝。
            if cost > 0:
                snapshot = self.store.get(player_id)["snapshot"]
                try:
                    self.economy._spend(player_id, snapshot, GOLD_ITEM, cost)
                except UnresolvedEconomy:
                    return _refused()
                self.economy._write_snapshot(player_id, snapshot)
            cursor = self.store.db.execute(
                """INSERT INTO club_wishes
                   (club_id,owner_uid,item_id,want_num,donate_num,got_num,limit_num,donate_count,time)
                   VALUES (?,?,?,?,0,0,?,0,?)""",
                (club_id, player_uid(player_id), item_id, want, want, int(now)))
            wish_id = cursor.lastrowid
            got = 0
            for index, entry in enumerate(ai_roster()[:AI_WISH_DONORS]):
                num = min(1 + index % 2, want - got)  # 每人 1~2 个, 且总数不超 want
                if num <= 0:
                    break
                # 延迟助力: 第 1/2/3 个人机分别在 now+60/90/120 秒才捐到。
                due = int(now) + AI_WISH_DELAY_MIN + index * AI_WISH_DELAY_STEP
                self.store.db.execute(
                    "INSERT INTO club_wish_donations (wish_id,donor_uid,num,time) VALUES (?,?,?,?)",
                    (wish_id, entry["uid"], num, due))
                got += num
            # wish 的 donate_num/got_num/donate_count 保持 0, 到点后由读取端结算。
        # 发布扣了金币 -> 补推一份 PlayerDataProto, 右上角金币/余额立刻刷新。
        return OutboundMessage("L2C_ClubWishing", {"code": CODE_OK, "itemId": item_id},
                               before_response=self._refresh_pushes(player_id),
                               pushes=self._item_push(player_id))

    def _ClubWishingCount(self, player_id: int, req: dict[str, Any], now: float):
        uid = player_uid(player_id)
        # wishingCount = 玩家今天**还在祈愿中**的条数 (自己发起、且还没收满 got_num<want_num)。
        # 客户端拿它判定该项「已祈愿」并把发布按钮置灰 —— 以前算的是"今天发过的条数", 于是
        # 祈愿一旦被助力收满 (2/2) 仍算作"已祈愿", 玩家明明不需要这个碎片也看到「已祈愿」
        # (用户实测图一)。已收满的祈愿不再占位。
        start, _ = day_period(int(now))
        wishing_count = self.store.db.execute(
            "SELECT count(*) FROM club_wishes WHERE owner_uid=? AND time>=? AND got_num<want_num",
            (uid, start)).fetchone()[0]
        # 赠送/受助力次数按**今日**统计 (以前赠送是全时段累计, 跨天不清零)。
        give = self.store.db.execute(
            "SELECT count(*) FROM club_wish_donations WHERE donor_uid=? AND time>=?",
            (uid, start)).fetchone()[0]
        help_cnt = self.store.db.execute(
            """SELECT count(*) FROM club_wish_donations d JOIN club_wishes w ON w.id=d.wish_id
               WHERE w.owner_uid=? AND d.time<=? AND d.time>=?""",
            (uid, int(now), start)).fetchone()[0]
        return OutboundMessage("L2C_ClubWishingCount", {
            "code": CODE_OK, "wishingCount": wishing_count,
            "guildWishGiveCount": give, "guildHelpPowerCount": help_cnt})

    def _resolve_wish(self, club_id: int, wishing_id: Any):
        """把客户端发来的 ``wishingId`` 解析成一条 club_wishes 行 (见 _ClubWishingDonate)。

        客户端实际发的是祈愿主人的**对外数字 uid** (抓包 2026-10-12: wishingId=1003 =
        ai1003), 不是行 id; 但为兼容其它路径, 先按主人 uid 取该成员在本社团的祈愿
        (每人机每个本地日恰好 1 条), 查不到再按行 id 回退。
        """
        try:
            numeric = int(wishing_id)
        except (TypeError, ValueError):
            return None
        owner = db_uid(str(numeric))
        row = self.store.db.execute(
            "SELECT * FROM club_wishes WHERE club_id=? AND owner_uid=? "
            "ORDER BY time DESC, id DESC LIMIT 1", (club_id, owner)).fetchone()
        if row is not None:
            return row
        return self.store.db.execute(
            "SELECT * FROM club_wishes WHERE club_id=? AND id=?", (club_id, numeric)).fetchone()

    def _ClubWishingDonate(self, player_id: int, req: dict[str, Any], now: float):
        """玩家给人机的祈愿捐赠: 校验背包 (数量≥2 的可堆叠材料) -> 扣 1 -> 给金币+学级积分。

        学级积分 (1237924) 必须同时进背包, 否则 807 社团商店页头余额恒 0、买不了东西
        (登录时 GuildScore 从背包回填); `_add_club_score` 只累加社团/成员总分。

        ``wishingId`` 的语义坑: 客户端发来的是祈愿主人的对外数字 uid (见 _resolve_wish),
        不是 ``club_wishes.id``。旧实现直接按行 id 查, 查不到 -> 一律 CODE_REFUSED, 用户点
        「赠送」就弹「操作失败」。回包里的 ``wishingId`` 原样回显客户端值。
        """
        request_id = req.get("wishingId", 0)
        club_id = self._club_id(player_id, now)
        row = self._resolve_wish(club_id, request_id)
        if row is None or row["owner_uid"] == player_uid(player_id):
            return OutboundMessage("L2C_ClubWishingDonate",
                                   {"code": CODE_REFUSED, "wishingId": request_id, "rewardData": b""})
        wish_id = int(row["id"])
        item_id = int(row["item_id"])
        qty = self.store.db.execute(
            "SELECT quantity FROM inventory WHERE player_id=? AND item_id=?",
            (player_id, item_id)).fetchone()
        if qty is None or int(qty[0]) < DONATE_MIN_QTY:
            return OutboundMessage("L2C_ClubWishingDonate",
                                   {"code": CODE_REFUSED, "wishingId": request_id, "rewardData": b""})
        rewards = {GOLD_ITEM: DONATE_GOLD, CLUB_SCORE_ITEM: DONATE_SCORE}
        try:
            with self.economy.transaction():
                self.store.db.execute(
                    "UPDATE inventory SET quantity=quantity-1 WHERE player_id=? AND item_id=?",
                    (player_id, item_id))
                cursor = self.store.db.execute(
                    "INSERT INTO club_wish_donations (wish_id,donor_uid,num,time) VALUES (?,?,?,?)",
                    (wish_id, player_uid(player_id), 1, int(now)))
                donation_id = int(cursor.lastrowid)
                self.store.db.execute("""UPDATE club_wishes SET donate_num=donate_num+1,
                    got_num=got_num+1, donate_count=donate_count+1 WHERE id=?""", (wish_id,))
                self._add_club_score(club_id, player_id, DONATE_SCORE)
                # 攻略「每次有人助力你, 双方都能获得学级积分」: 捐赠方(玩家)在上一步拿分,
                # 祈愿主人(人机)也按 uid 记一份成员积分 (总分不重复计入 clubs)。
                self._add_member_score(club_id, str(row["owner_uid"]), DONATE_SCORE)
                # 幂等键必须**逐次捐赠**唯一: 旧键 (wish_id:player_id) 会把同一个祈愿下的
                # 第 2、3 次捐赠折叠成同一条 —— _grant 命中旧记录时直接返回旧 rewards 不再入账,
                # 于是"捐两次只拿到一次金币+学级积分"(用户实测)。绑上捐赠行 id 后每次捐赠各记一笔。
                self.economy._grant(player_id,
                    f"club:wishdonate:{wish_id}:{player_id}:{donation_id}", rewards)
        except UnresolvedEconomy:
            return OutboundMessage("L2C_ClubWishingDonate",
                                   {"code": CODE_REFUSED, "wishingId": request_id, "rewardData": b""})
        # 捐赠给了金币 + 学级积分 (都进背包): 必须补推一份 PlayerDataProto, 右上角学级积分
        # 才会立刻跳动 —— GuildScore 只在 snapshot_push 时从背包回填 (见 login.py), 而
        # L2C_ItemUpdate 让背包里的 1237924 也同步。用户实测的"横幅出现但右上角不变"就是这个。
        return OutboundMessage("L2C_ClubWishingDonate", {
            "code": CODE_OK, "wishingId": request_id,
            "rewardData": self.economy.reward_bytes(rewards)},
            before_response=self._refresh_pushes(player_id),
            pushes=self._item_push(player_id))

    def _ClubWishingReceive(self, player_id: int, req: dict[str, Any], now: float):
        """领取人机捐给自己的碎片 (发到 inventory)。同时支持「领取单条」与「一键领取」。

        客户端 ``C2L_ClubWishingReceive`` 只有 (donateId, time) 两个字段, 而它拿到的
        祈愿 DTO ``ClubMemberWishing`` 里只有 Wid/Donors(无 id), 所以 ``donateId`` 到底
        指哪一层**无法从 DTO 反推** (本地抓包里也从没出现过 768 —— 旧实现把整行"收满"
        收掉了, 玩家根本点不到领取, 用户实测图). 这里对三种可能全部兼容, 命中即领:
          1) donateId = club_wish_donations.id  (真正的"捐赠行")
          2) donateId = club_wishes.id          (客户端把它当"这次祈愿"的 id)
          3) donateId = 助力者的对外数字 uid (1003 -> ai1003)
        另外 donateId<=0 视为「一键领取」: 把我自己所有"已到点且未领取"的助力一次收完
        (客户端字符串里有「当前没有可一键领取的」、「不会出现领取许愿但是又没有许愿数据的情况」,
        对应 ClubModule_SendWishingReceive_1)。

        攻略「每次有人助力你, 双方都能获得学级积分」: 玩家是祈愿主人, 收下的同时也拿
        DONATE_SCORE 学级积分 (进背包, 由回包补推快照刷右上角); 助力的人机同样按 uid 记分。
        """
        try:
            donate_id = int(req.get("donateId", 0) or 0)
        except (TypeError, ValueError):
            donate_id = 0

        def _refused():
            return OutboundMessage("L2C_ClubWishingReceive",
                                   {"code": CODE_REFUSED, "donateId": donate_id, "rewardData": b""})

        # 候选 = 我自己祈愿下、已到点、还没被领走的助力 (未到点的是"还在路上", 不能领)。
        rows = self.store.db.execute(
            """SELECT d.id AS did,d.num,d.donor_uid,w.id AS wish_id,w.club_id,w.item_id
               FROM club_wish_donations d JOIN club_wishes w ON w.id=d.wish_id
               WHERE w.owner_uid=? AND d.received=0 AND d.time<=? ORDER BY d.id""",
            (player_uid(player_id), int(now))).fetchall()
        picked = []
        if donate_id <= 0:
            picked = list(rows)                       # 一键领取
        else:
            picked = [r for r in rows if int(r["did"]) == donate_id]
            if not picked:                            # 客户端把 donateId 当祈愿行 id
                picked = [r for r in rows if int(r["wish_id"]) == donate_id]
            if not picked:                            # 客户端把 donateId 当助力者的 uid
                donor = db_uid(str(donate_id))
                picked = [r for r in rows if str(r["donor_uid"]) == donor]
        if not picked:
            return _refused()

        # 同一条祈愿下的助力一起领 (一个祈愿最多 2~3 条); 聚合奖励避免重复项被覆盖。
        ids = [int(r["did"]) for r in picked]
        rewards: dict[int, int] = {}
        for r in picked:
            item = int(r["item_id"])
            rewards[item] = rewards.get(item, 0) + int(r["num"])
        rewards[CLUB_SCORE_ITEM] = rewards.get(CLUB_SCORE_ITEM, 0) + DONATE_SCORE * len(picked)
        club_id = int(picked[0]["club_id"])
        marks = ",".join("?" * len(ids))
        try:
            with self.economy.transaction():
                self.store.db.execute(
                    f"UPDATE club_wish_donations SET received=1 WHERE id IN ({marks})", ids)
                for r in picked:
                    self._add_club_score(club_id, player_id, DONATE_SCORE)
                    self._add_member_score(club_id, str(r["donor_uid"]), DONATE_SCORE)
                self.economy._grant(player_id, f"club:donation:{ids[0]}", rewards)
                # 领完立刻重算该社团的 wish 计数, 让客户端刷新后看到 GotNum 涨、按钮消失。
                _settle_due_donations(self.store.db, club_id, now)
        except UnresolvedEconomy:
            return _refused()
        return OutboundMessage("L2C_ClubWishingReceive", {
            "code": CODE_OK, "donateId": donate_id,
            "rewardData": self.economy.reward_bytes(rewards)},
            before_response=self._refresh_pushes(player_id),
            pushes=self._item_push(player_id))

    _dispatch = {
        "C2L_CreateClub": _CreateClub, "C2L_RecommandClub": _RecommandClub,
        "C2L_AppalyJoinClub": _AppalyJoinClub, "C2L_QuickJoinClub": _QuickJoinClub,
        "C2L_UpdateClubInfo": _UpdateClubInfo, "C2L_UpdateClubRecruit": _UpdateClubRecruit,
        "C2L_JoinClubListner": _JoinClubListner, "C2L_ClubApproval": _ClubApproval,
        "C2L_UpdateMemberPrivilege": _UpdateMemberPrivilege, "C2L_DismissMember": _DismissMember,
        "C2L_QuitClub": _QuitClub, "C2L_ClubActiMainData": _ClubActiMainData,
        "C2L_ClubWishing": _ClubWishing, "C2L_ClubWishingCount": _ClubWishingCount,
        "C2L_ClubWishingDonate": _ClubWishingDonate,
        "C2L_ClubWishingReceive": _ClubWishingReceive, "C2L_ClubReceiveReward": _ClubReceiveReward,
    }