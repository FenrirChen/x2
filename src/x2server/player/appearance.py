"""Owned appearance catalog and persistent equipped state."""
from importlib.resources import files
import json
import logging

from x2server.messages.appearance import (APPEARANCE_SCHEMAS as SCHEMAS, HERO_SKIN,
    HERO_DUBBING_DATA, SEASON_ICON_DATA, ICON_INFO, PICTURE_ID_ENTRY)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

DEFAULT_HEAD_ICON = 1000001
HEAD_ICON_Q_FAVOR_LEVEL = 10
_HEAD_ICON_CATALOG = None


def head_icon_catalog():
    global _HEAD_ICON_CATALOG
    if _HEAD_ICON_CATALOG is None:
        _HEAD_ICON_CATALOG = json.loads(files("x2server").joinpath("data/head_icons.json").read_text(encoding="utf-8"))
    return _HEAD_ICON_CATALOG


def granted_head_icons(snapshot, favors=None):
    return json.loads(files("x2server").joinpath("data/appearance_catalog.json").read_text(encoding="utf-8"))["head_icons"]


def avatar_frames():
    return {r["ItemID"] for r in json.loads(files("x2server").joinpath("data/reward_items.json").read_text(encoding="utf-8"))
            if r.get("ItemType", {}).get("value") == 20}


def head_icon_info(snapshot, favors=None):
    icons = granted_head_icons(snapshot, favors)
    return ICON_INFO.encode({"IconType": 1, "IconID": int(snapshot.get("head_icon", DEFAULT_HEAD_ICON) or DEFAULT_HEAD_ICON),
        "OrnamentID": snapshot.get("avatar_frame", 0), "PictureID": [PICTURE_ID_ENTRY.encode({"Key": i, "Value": value})
            for i, value in enumerate(icons)]})


# 触碰语音 (Dubbing) 解锁条件: 条件编号即客户端文案 id, 逐条照搬官方
# (x2offline/src/offline/mission.cpp kDubbingCondRules / dubbing_unlock_ids):
#   auto  离线/单服没有对应事件触发源(契约/连续登录/节日/生日/默认) -> 直接放行
#   break 默契度第 N 次突破后解锁 (favor_breaks 条数 >= N)
#   level 默契度 N 级后点击解锁 (favor.level >= N)
#   click 需玩家点击(点击解锁/收到喜欢的礼物) 由 C2L_SaveHeroDubbing 落库
DUBBING_COND_RULES = {
    1350101: ("click", 0),   # [点击解锁]
    1350102: ("break", 1),   # [默契度第1次突破后解锁]
    1350103: ("break", 2),   # [默契度第2次突破后解锁]
    1350104: ("break", 3),   # [默契度第3次突破后解锁]
    1350105: ("auto", 0),    # [契约后解锁]
    1350106: ("auto", 0),    # [连续登录3天点击解锁]
    1350107: ("auto", 0),    # [连续登录7天点击解锁]
    1350108: ("auto", 0),    # [连续登录30天点击解锁]
    1350109: ("auto", 0),    # [累计登录50天点击解锁]
    1350110: ("auto", 0),    # [累计登录100天点击解锁]
    1350111: ("click", 0),   # [收到喜欢的礼物解锁]
    1350112: ("auto", 0),    # [元旦解锁]
    1350113: ("auto", 0),    # [春节解锁]
    1350114: ("auto", 0),    # [情人节解锁]
    1350115: ("auto", 0),    # [愚人节解锁]
    1350116: ("auto", 0),    # [儿童节解锁]
    1350117: ("auto", 0),    # [夏日祭解锁]
    1350118: ("auto", 0),    # [返校季解锁]
    1350119: ("auto", 0),    # [秋日祭解锁]
    1350120: ("auto", 0),    # [冬日祭解锁]
    1350121: ("auto", 0),    # [神格生日解锁]
    1350122: ("auto", 0),    # [解神者生日解锁]
    1350123: ("auto", 0),    # [默认解锁]
    1350124: ("level", 5),   # [默契度5级后点击解锁]
}


def dubbing_condition_kind(condition):
    rule = DUBBING_COND_RULES.get(condition)
    return rule[0] if rule else None


def dubbing_unlocked(condition, hero, saved_ids, dubbing_id):
    """按官方规则判断一条语音是否解锁 (含玩家既往点击落库)。"""
    if dubbing_id in saved_ids:
        return True
    rule = DUBBING_COND_RULES.get(condition)
    if rule is None:
        return False
    kind, param = rule
    if kind == "auto":
        return True
    if kind == "break":
        return len(hero.get("favor_breaks", [])) >= param
    if kind == "level":
        return hero.get("favor", {}).get("level", 1) >= param
    return False  # click: 需玩家点击后 C2L_SaveHeroDubbing 落库


class AppearanceService:
    def __init__(self, store, economy):
        self.store, self.economy = store, economy
        data = json.loads(files("x2server").joinpath("data/appearance_catalog.json").read_text(encoding="utf-8"))
        self.skins = {r["id"]: r for r in data["appearance"]}
        self.voices = {r["id"]: r for r in data["dubbing"]}
        self.heads, self.scenes = set(data["head_icons"]), set(data["scene_icons"])
        self.starter_head = data["starter_head_icon"]
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS appearance_wear (
                player_id INTEGER NOT NULL, hero_id INTEGER NOT NULL, type INTEGER NOT NULL,
                skin_id INTEGER NOT NULL, PRIMARY KEY(player_id,hero_id,type))""")
            store.db.execute("""CREATE TABLE IF NOT EXISTS appearance_voice_unlock (
                player_id INTEGER NOT NULL, dubbing_id INTEGER NOT NULL,
                PRIMARY KEY(player_id,dubbing_id))""")
            # Native SendApplySkin: 1=battle, 2=outer, 3=both. Earlier
            # compatibility code mistakenly persisted 3 as an outer-only slot.
            # Preserve explicit slots (their relative write order is unknown).
            for slot in (1, 2):
                store.db.execute("""INSERT OR IGNORE INTO appearance_wear
                    SELECT player_id,hero_id,?,skin_id FROM appearance_wear WHERE type=3""", (slot,))
            store.db.execute("DELETE FROM appearance_wear WHERE type=3")

    def handlers(self):
        return {"C2L_" + name: self.handle for name in (
            "Account", "HeroSkinAll", "HeroWearSkin", "SeasonIcon", "PutOnOrPutOffSeasonIcon",
            "SeasonIconStatusUp", "QueryHeroDubbing", "SaveHeroDubbing")}

    def _owned_heroes(self, player_id):
        return {h["id"] for h in self.store.get(player_id)["snapshot"].get("heroes", []) if h.get("state") == 2}

    def _inventory(self, player_id):
        return {r[0] for r in self.store.db.execute(
            "SELECT item_id FROM inventory WHERE player_id=? AND quantity>0", (player_id,))}

    def _owned_skins(self, player_id):
        heroes = {h["id"]: h for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                  if h.get("state") == 2}
        items = self._inventory(player_id)
        # PlayerStage 11 is the first five-star stage in the client table.
        return {i for i, r in self.skins.items() if r["hero_id"] in heroes and
                (r["acquire"] == "E_Default" or i in items or
                 r["acquire"] == "E_Stage" and heroes[r["hero_id"]].get("star", 0) >= 11)}

    def skin_values(self, player_id):
        owned = self._owned_skins(player_id)
        worn = {(r[0], r[1]): r[2] for r in self.store.db.execute(
            "SELECT hero_id,type,skin_id FROM appearance_wear WHERE player_id=?", (player_id,))}
        return {"skinList": [HERO_SKIN.encode({"heroId": hero,
            "skinIds": sorted(i for i in owned if self.skins[i]["hero_id"] == hero),
            "battleSkin": worn.get((hero, 1), 0), "outerSkin": worn.get((hero, 2), 0)})
            for hero in sorted(self._owned_heroes(player_id))]}

    def _icon_values(self, player_id):
        items = self._inventory(player_id)
        snapshot = self.store.get(player_id)["snapshot"]
        favors = {int(hero["id"]): hero.get("favor", {})
                  for hero in snapshot.get("heroes", [])}
        heads = self.heads | {self.starter_head}
        scenes = self.scenes
        return {"code": 10,
            "putOnHeadIcon": snapshot.get("head_icon", self.starter_head),
            "putOnSceneIcon": snapshot.get("scene_icon", 0),
            # Compatibility: permanently opened catalogs are already seen.
            # Client AccountInfoModule marks rankId == 0 as new.
            "headIconList": [SEASON_ICON_DATA.encode({"id": i, "rankId": 1}) for i in sorted(heads)],
            "sceneIconList": [SEASON_ICON_DATA.encode({"id": i, "rankId": 1}) for i in sorted(scenes)]}

    def _voice_values(self, player_id):
        heroes = {h["id"]: h for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                  if h.get("state") == 2}
        saved = {r[0] for r in self.store.db.execute(
            "SELECT dubbing_id FROM appearance_voice_unlock WHERE player_id=?", (player_id,))}
        return {"code": 10, "heroDubbingDatas": [HERO_DUBBING_DATA.encode({
            "heroId": hero, "dubbingIds": sorted(i for i, r in self.voices.items()
                if r["hero_id"] == hero and dubbing_unlocked(r["unlock_condition"], heroes[hero], saved, i))})
            for hero in sorted(heroes)]}

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("appearance requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        req = SCHEMAS[name].decode(packet.body) if name in SCHEMAS else {}
        if name == "C2L_Account":
            opt, values = req.get("opt", -1), req.get("values", [])
            logging.getLogger("x2.appearance").info(
                "account update player=%s opt=%s values=%s strvals=%s", player_id, opt, values, req.get("strvals", []))
            if opt == 3:
                if len(values) != 2 or values[0] <= 0 or values[1] < 0:
                    return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    groups = snapshot.setdefault("guide_groups", {})
                    old = groups.get(str(values[0]))
                    if old is not None and old != values[1]:
                        return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                    groups[str(values[0])] = values[1]
                    self.economy.save_snapshot(player_id, snapshot)
                logging.getLogger("x2.tutorial").info("guide group player=%s group=%s next=%s",
                    player_id, values[0], values[1])
                return OutboundMessage("L2C_Account", {"result": 10, "opt": opt},
                    before_response=(self.economy.pushes(player_id)[0],))
            if opt == 7:
                names = req.get("strvals", [])
                if len(names) != 1 or not names[0].strip() or len(names[0]) > 16 or any(
                        not char.isprintable() for char in names[0]):
                    return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                requested = names[0]
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    from .naming import nickname_count
                    current = snapshot.get("nickname", "")
                    count = nickname_count(snapshot)
                    if count and current != requested:
                        return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                    if not count or snapshot.get('nick_count') != count:
                        # Persist the marker together with the name, before the
                        # response unpauses the plot. A retry must not count twice.
                        snapshot["nickname"] = requested
                        snapshot["nick_count"] = max(1, count)
                        self.economy.save_snapshot(player_id, snapshot)
                logging.getLogger("x2.tutorial").info("first name player=%s set=%s", player_id, not current)
                return OutboundMessage("L2C_Account", {"result": 10, "opt": opt},
                    before_response=(self.economy.pushes(player_id)[0],))
            # 设置/取消「喜爱的神格」：神格详情页右上角那枚叠层菱形图标。客户端
            # AccountInfoModule.HeroIsEnjoy(heroId, isEnjoy) 把 isEnjoy 折成这两档
            # （tst/csinc：isEnjoy 时 opt 5「设置」，否则 opt 6「取消」），values 只带那一个
            # 神格 id；成功回包让客户端弹 430004「设置为喜爱的神格」/ 430005
            # 「不再设置为喜爱的神格」。状态存在该神格自己的 HeroData.Enjoy 上——列表项的
            # 置顶标记 (HeroEntryListItem_RefreshItem: SetActive(Enjoy > 0)) 和列表排序
            # (HeroModule_ShowSortRule) 都读它，所以必须排在回包之前下发，否则横幅会弹而
            # 列表不动。不认这两档就回 13，也就是客户端看到的「操作失败 E_ERROR_OPT」。
            if opt in (5, 6):
                if len(values) != 1:
                    return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                enjoy = 1 if opt == 5 else 0
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    hero = next((h for h in snapshot.get("heroes", [])
                                 if h["id"] == values[0] and h.get("state") == 2), None)
                    if hero is None:
                        return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                    hero["enjoy"] = enjoy
                    self.economy.save_snapshot(player_id, snapshot)
                from .hero import encode_hero_data
                heroes = [encode_hero_data(h, season=self.economy.season, player_id=player_id)
                          for h in self.store.get(player_id)["snapshot"].get("heroes", [])]
                logging.getLogger("x2.appearance").info(
                    "喜爱神格 player=%s hero=%s enjoy=%s", player_id, values[0], enjoy)
                return OutboundMessage("L2C_Account", {"result": 10, "opt": opt}, before_response=(
                    OutboundMessage("L2C_HeroUpdate", {"code": 10, "heros": heroes}),))
            # The 2.4 avatar picker sends the selected id together with a
            # second decoration/slot value in ``values``.  The server only
            # owns the selected id; rejecting the otherwise valid packet
            # makes every avatar change appear to fail with code 13.
            if opt not in (1, 2) or not values:
                return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
            if opt == 2 and len(values) == 3 and values[0] == 1:
                frame = values[2]
                if frame != 0 and frame not in avatar_frames():
                    return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
                with self.economy.transaction():
                    snapshot = self.store.get(player_id)["snapshot"]
                    snapshot["avatar_frame"] = frame
                    self.economy.save_snapshot(player_id, snapshot)
                return OutboundMessage("L2C_Account", {"result": 10, "opt": opt}, before_response=(self.economy.pushes(player_id)[0],))
            owned = (self._owned_heroes(player_id) if opt == 1 else
                set(granted_head_icons(self.store.get(player_id)["snapshot"], {
                    int(hero["id"]): hero.get("favor", {})
                    for hero in self.store.get(player_id)["snapshot"].get("heroes", [])})) |
                {SEASON_ICON_DATA.decode(x)["id"] for x in self._icon_values(player_id)["headIconList"]})
            selected = next((int(value) for value in values if int(value) in owned), None)
            if selected is None:
                return OutboundMessage("L2C_Account", {"result": 13, "opt": opt})
            with self.economy.transaction():
                snapshot = self.store.get(player_id)["snapshot"]
                snapshot["show" if opt == 1 else "head_icon"] = selected
                self.economy.save_snapshot(player_id, snapshot)
            update = (self.economy.pushes(player_id)[0],)
            # The picker marks "in use" from state that the PlayerDataProto push
            # carries (IconInfo.IconID / Show). Deliver it before the response
            # frame, like every other Account option, so the open page re-renders
            # with the new value instead of needing a page re-entry.
            return OutboundMessage("L2C_Account", {"result": 10, "opt": opt},
                                   before_response=update)
        if name == "C2L_HeroSkinAll":
            return OutboundMessage("L2C_HeroSkinAll", self.skin_values(player_id))
        if name == "C2L_SeasonIcon":
            return OutboundMessage("L2C_SeasonIcon", self._icon_values(player_id))
        if name == "C2L_QueryHeroDubbing":
            return OutboundMessage("L2C_QueryHeroDubbing", self._voice_values(player_id))
        if name == "C2L_SaveHeroDubbing":
            voice = self.voices.get(req.get("dubbingId"))
            hero = next((h for h in self.store.get(player_id)["snapshot"].get("heroes", [])
                if h["id"] == req.get("heroId") and h.get("state") == 2), None)
            if not voice or not hero or voice["hero_id"] != hero["id"]:
                return OutboundMessage("L2C_SaveHeroDubbing", {"code": 13, "heroDubbingDatas": []})
            condition = voice["unlock_condition"]
            kind = dubbing_condition_kind(condition)
            saved = {r[0] for r in self.store.db.execute(
                "SELECT dubbing_id FROM appearance_voice_unlock WHERE player_id=?", (player_id,))}
            # [点击解锁]/[收到喜欢的礼物] 由客户端点击触发, 其余条件(默认/突破/等级)
            # 只要已满足即可确认; 未知条件保持锁死 (官方 kDubbingCondRules 之外不放行)。
            allowed = kind == "click" or dubbing_unlocked(condition, hero, saved, req["dubbingId"])
            if kind == "click" and allowed and req["dubbingId"] not in saved:
                with self.economy.transaction():
                    self.store.db.execute("INSERT OR IGNORE INTO appearance_voice_unlock VALUES (?,?)",
                                          (player_id, req["dubbingId"]))
            return OutboundMessage("L2C_SaveHeroDubbing", {
                "code": 10 if allowed else 13,
                "heroDubbingDatas": self._voice_values(player_id)["heroDubbingDatas"] if allowed else []})
        if name == "C2L_HeroWearSkin":
            hero, skin, kind = req.get("heroId"), req.get("skinId"), req.get("type")
            valid = (kind in (1, 2, 3) and skin in self._owned_skins(player_id) and
                     self.skins[skin]["hero_id"] == hero)
            if not valid:
                logging.getLogger("x2.appearance").info(
                    "skin wear denied player=%s hero=%s skin=%s type=%s reason=invalid_or_unowned",
                    player_id, hero, skin, kind)
                return OutboundMessage("L2C_HeroWearSkin", {"code": 13,
                    "heroId": hero or 0, "skinId": skin or 0, "type": kind or 0})
            with self.economy.transaction():
                for slot in ((1, 2) if kind == 3 else (kind,)):
                    self.store.db.execute("INSERT OR REPLACE INTO appearance_wear VALUES (?,?,?,?)",
                                          (player_id, hero, slot, skin))
            logging.getLogger("x2.appearance").info(
                "skin wear saved player=%s hero=%s skin=%s type=%s database=%s",
                player_id, hero, skin, kind, self.store.path.resolve())
            # The client handles wear success by firing a UI event only. Its
            # equipped-skin cache is updated by L2C_HeroSkinUpdate, so deliver
            # the new HeroSkin before the success event is processed.
            updated = next(value for value in self.skin_values(player_id)["skinList"]
                           if HERO_SKIN.decode(value)["heroId"] == hero)
            return OutboundMessage("L2C_HeroWearSkin", {"code": 10,
                "heroId": hero, "skinId": skin, "type": kind},
                before_response=(OutboundMessage("L2C_HeroSkinUpdate", {"skin": updated}),))
        if name == "C2L_PutOnOrPutOffSeasonIcon":
            kind, icon = req.get("type"), req.get("id")
            owned = self._icon_values(player_id)
            allowed = ({SEASON_ICON_DATA.decode(x)["id"] for x in owned["headIconList"]}
                       if kind == 1 else {SEASON_ICON_DATA.decode(x)["id"] for x in owned["sceneIconList"]}
                       if kind == 2 else set())
            # 场景展示页切回默认场景走 type=3: SceneSettingTab_OnMBtnSaveClick 在选中列表第 0 项时
            # 把当前佩戴的场景 id 一起带上来, 语义是"卸下场景"而不是"再戴一次"。原实现把 type=3
            # 归进 allowed = set(), 于是必然命中下面的 code 13; 客户端只在 code==10 时才调
            # RefreshSceneSkin 去写 PlayerPrefs("SceneSkin"+玩家号), 结果就是背景能切过去、
            # 切不回默认。type 只有 2/3 两档 (换头像走 C2L_Account opt=2, 不走这条消息)。
            if kind == 3:
                icon = 0
            elif icon not in allowed and not (icon == 0 and kind == 2):
                return OutboundMessage("L2C_PutOnOrPutOffSeasonIcon", {"code": 13})
            with self.economy.transaction():
                snapshot = self.store.get(player_id)["snapshot"]
                snapshot["head_icon" if kind == 1 else "scene_icon"] = icon
                self.economy.save_snapshot(player_id, snapshot)
            owned = self._icon_values(player_id)
            return OutboundMessage("L2C_PutOnOrPutOffSeasonIcon", {k: owned[k] for k in
                ("code", "putOnHeadIcon", "putOnSceneIcon")},
                pushes=(self.economy.pushes(player_id)[0],))
        if name == "C2L_SeasonIconStatusUp":
            return OutboundMessage("L2C_SeasonIconStatusUp", {
                "code": 13, "type": req.get("type", 0), "id": req.get("id", 0)})
        raise ProtocolError("unknown appearance request")
