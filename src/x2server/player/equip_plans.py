"""兽主套装预设 (EquipPlan) 的持久化与应答。

这套协议（C2L_UpdateEquipPlan 423 … C2L_UseEquipPlan 429）对应客户端预设页的
保存/置顶/删除/应用四个动作。数据存进玩家快照的一个键里
（``snapshot['equip_plans']``），与星图同一种做法：

    {"next_id": 1,
     "plans": {"1": {"name": "输出", "set_top_time": 0,
                     "positions": {"0": 1234001, "1": 1234002}}},
     "deleted": [3, 4]}

删除保留一条墓碑（``deleted``）：客户端的 PlayerData 合并按预设 id 建字典，必须把被删
的 id 继续下发一次（``val`` 缺席）才能让它把本地那条抹掉。见 messages/equip_plan.py。
"""
import logging

from x2server.messages.equip_plan import (EQUIP_PLAN, EQUIP_PLAN_SCHEMAS, PLAN,
                                          PLAN_ENTRY, PLAN_POS)
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from .hero import encode_hero_data
from .server_clock import ServerClock

LOGGER = logging.getLogger("x2.equip_plan")

# 预设 id 上界，与客户端预设页对 id 的判定 (0 <= id < 0x10000) 一致。
MAX_PLAN_ID = 0x10000


def state(snapshot):
    """取出（必要时新建）玩家快照里的预设状态，返回可写字典。"""
    current = snapshot.get("equip_plans")
    if not isinstance(current, dict):
        current = {"next_id": 1, "plans": {}, "deleted": []}
        snapshot["equip_plans"] = current
    current.setdefault("next_id", 1)
    current.setdefault("plans", {})
    current.setdefault("deleted", [])
    return current


def snapshot_value(snapshot):
    """PlayerDataProto 字段 9 的编码结果，删除墓碑一并下发。

    永远返回一个（可能为空的）EquipPlanProto：repeated 成员缺席会被这个客户端的
    解码器变成 null，而这个键在每次带 store 的快照推送里都要出现——和 StarMap、
    MedalSystem 同一约定（见 player/login.snapshot_push）。
    """
    current = snapshot.get("equip_plans") or {}
    plans = current.get("plans") or {}
    entries = []
    for plan_id in sorted(plans, key=int):
        plan = plans[plan_id] or {}
        entries.append(PLAN_ENTRY.encode({
            "Key": int(plan_id),
            "Val": PLAN.encode({
                "Name": plan.get("name", ""),
                "SetTopTime": int(plan.get("set_top_time", 0)),
                "Position": [PLAN_POS.encode({"Key": int(slot), "Value": int(equip_id)})
                             for slot, equip_id in sorted(
                                 (plan.get("positions") or {}).items(),
                                 key=lambda pair: int(pair[0]))],
            }),
        }))
    known = {int(plan_id) for plan_id in plans}
    for plan_id in current.get("deleted") or []:
        if int(plan_id) not in known:
            entries.append(PLAN_ENTRY.encode({"Key": int(plan_id)}))
    return EQUIP_PLAN.encode({"Plan": entries})


class EquipPlanService:
    def __init__(self, store, economy=None, equipment=None, clock=None):
        self.store = store
        self.economy = economy
        # 应用预设要用装备的部件表 (type_id -> part) 校验槽位，并推 L2C_EquipUpdate；
        # 都由 EquipmentService 提供。可选，缺省时 UseEquipPlan 只做槽位自洽的应用。
        self.equipment = equipment
        self.clock = clock or ServerClock()

    def handlers(self):
        return {name: self.handle for name in EQUIP_PLAN_SCHEMAS if name.startswith("C2L_")}

    async def handle(self, context, packet):
        player_id = context.session.player_id
        if player_id is None:
            raise ProtocolError("equip plan requested before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        request = EQUIP_PLAN_SCHEMAS[name].decode(packet.body)
        if name == "C2L_UpdateEquipPlan":
            return self.save(player_id, request)
        if name == "C2L_SetTopEquipPlan":
            return self.set_top(player_id, request)
        if name == "C2L_DelEquipPlan":
            return self.delete(player_id, request)
        return self.use(player_id, request)

    def owned_equipment(self, player_id):
        return {int(row[0]): int(row[1]) for row in self.store.db.execute(
            "SELECT id,type_id FROM equipment_instances WHERE player_id=?", (player_id,))}

    def snapshot_push(self, player_id):
        """一份完整的 PlayerDataProto 推送：预设列表（含墓碑）就挂在字段 9 上。"""
        from .login import LoginService
        return LoginService.snapshot_push(self.store.get(player_id), store=self.store)

    def save(self, player_id, request):
        """C2L_UpdateEquipPlan (423) -> L2C_UpdateEquipPlan (424)。

        ``planId`` 为 0 表示新建，服务端分配下一个空闲 id（用自增游标，删掉中间某个
        预设也不会复用它的 id）。
        """
        plan_id = int(request.get("planId", 0))
        owned = self.owned_equipment(player_id)
        positions = {}
        for raw in request.get("pos", []):
            entry = PLAN_POS.decode(raw)
            slot = int(entry.get("Key", 0))
            equip_id = int(entry.get("Value", 0))
            if slot < 0 or equip_id <= 0 or equip_id not in owned:
                continue
            positions[str(slot)] = equip_id
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        current = state(snapshot)
        if plan_id <= 0:
            plan_id = int(current["next_id"])
            current["next_id"] = plan_id + 1
        elif plan_id >= MAX_PLAN_ID:
            return OutboundMessage("L2C_UpdateEquipPlan", {"code": 13, "planId": plan_id})
        previous = current["plans"].get(str(plan_id)) or {}
        current["plans"][str(plan_id)] = {
            "name": request.get("name", "") or "",
            "set_top_time": int(previous.get("set_top_time", 0)),
            "positions": positions,
        }
        current["deleted"] = [i for i in current["deleted"] if int(i) != plan_id]
        self.store.save_snapshot(player_id, snapshot, player["revision"])
        LOGGER.info("equip plan saved player=%s id=%s slots=%s name=%s",
                    player_id, plan_id, len(positions), current["plans"][str(plan_id)]["name"])
        # 客户端一处理完这个回包就会重画预设页，所以带字段 9 的 PlayerDataProto 必须
        # 先到，否则它读到的是还没有这条新预设的旧缓存（要退出页面再进才看得到）。
        # before_response 让推送排在回包之前，同 appearance/equipment 的先例。
        return OutboundMessage("L2C_UpdateEquipPlan", {"code": 10, "planId": plan_id},
                               before_response=(self.snapshot_push(player_id),))

    def set_top(self, player_id, request):
        """C2L_SetTopEquipPlan (425) -> L2C_SetTopEquipPlan (426)。

        ``SetTopTime`` 是客户端排序用的置顶时间：置顶写当前时间，取消写 0。只改这一个
        预设——客户端是按时间排序展示的，允许同时置顶多个（各自时间不同）。
        """
        plan_id = int(request.get("planId", 0))
        is_top = bool(request.get("isTop", False))
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        current = state(snapshot)
        plan = current["plans"].get(str(plan_id))
        if plan is None:
            return OutboundMessage("L2C_SetTopEquipPlan", {"code": 13, "planId": plan_id})
        plan["set_top_time"] = int(self.clock.now()) if is_top else 0
        self.store.save_snapshot(player_id, snapshot, player["revision"])
        LOGGER.info("equip plan top player=%s id=%s isTop=%s", player_id, plan_id, is_top)
        # 同 save：置顶时间在字段 9 里，客户端要在回包之前就看到新排序。
        return OutboundMessage("L2C_SetTopEquipPlan", {"code": 10, "planId": plan_id},
                               before_response=(self.snapshot_push(player_id),))

    def delete(self, player_id, request):
        """C2L_DelEquipPlan (427) -> L2C_DelEquipPlan (428)。

        删除后 id 进墓碑列表，随下一次 PlayerData 推送继续下发一次；重复删除同一个 id
        是幂等的。
        """
        plan_id = int(request.get("planId", 0))
        if not 0 <= plan_id < MAX_PLAN_ID:
            return OutboundMessage("L2C_DelEquipPlan", {"code": 13, "planId": plan_id})
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        current = state(snapshot)
        current["plans"].pop(str(plan_id), None)
        if plan_id not in [int(i) for i in current["deleted"]]:
            current["deleted"].append(plan_id)
        self.store.save_snapshot(player_id, snapshot, player["revision"])
        LOGGER.info("equip plan deleted player=%s id=%s", player_id, plan_id)
        # 同 save：删除墓碑也要在回包之前随字段 9 下发，列表才会立刻少一条。
        return OutboundMessage("L2C_DelEquipPlan", {"code": 10, "planId": plan_id},
                               before_response=(self.snapshot_push(player_id),))

    def use(self, player_id, request):
        """C2L_UseEquipPlan (429) -> L2C_UseEquipPlan (430)。

        把预设里的装备一键穿到目标神格身上：方案里的每个 (slot, equipId) 先按装备自身
        的部件校验槽位是否自洽（部件号 - 1 == slot），再把该装备从其它神格身上摘下来、
        清掉目标神格同一槽位的旧装备，最后穿上。任何一件都不合法时拒绝整个请求。
        """
        plan_id = int(request.get("planId", 0))
        hero_id = int(request.get("heroId", 0))
        values = {"code": 13, "planId": plan_id, "heroId": hero_id}
        player = self.store.get(player_id)
        snapshot = player["snapshot"]
        plan = state(snapshot)["plans"].get(str(plan_id))
        if plan is None:
            return OutboundMessage("L2C_UseEquipPlan", values)
        hero = next((h for h in snapshot.get("heroes", [])
                     if h["id"] == hero_id and h["state"] == 2), None)
        if hero is None:
            return OutboundMessage("L2C_UseEquipPlan", values)
        parts = getattr(self.equipment, "parts", None)
        owned = self.owned_equipment(player_id)
        worn = []
        for slot, equip_id in sorted((plan.get("positions") or {}).items(),
                                     key=lambda pair: int(pair[0])):
            type_id = owned.get(int(equip_id))
            if type_id is None:
                continue
            # 没有部件表 (测试替身) 时跳过槽位校验，只要求装备属于本玩家。
            if parts is not None and parts.get(type_id, 0) - 1 != int(slot):
                continue
            worn.append({"position": int(slot), "equip_id": int(equip_id)})
        if not worn:
            return OutboundMessage("L2C_UseEquipPlan", values)
        ids = {e["equip_id"] for e in worn}
        slots = {e["position"] for e in worn}
        for other in snapshot.get("heroes", []):
            other["equips"] = [e for e in other.get("equips", [])
                               if e["equip_id"] not in ids]
        hero["equips"] = [e for e in hero.get("equips", []) if e["position"] not in slots]
        hero["equips"].extend(worn)
        self.store.save_snapshot(player_id, snapshot, player["revision"])
        values["code"] = 10
        LOGGER.info("equip plan used player=%s id=%s hero=%s equips=%s",
                    player_id, plan_id, hero_id, len(worn))
        # 同 save：客户端是在处理这个回包的那一刻重画神格身上的兽主图标的，
        # 所以带新穿戴状态的推送必须排在回包之前；排在之后 (=pushes) 它读到的
        # 还是换装前的缓存，兽主图标要退出页面再进才会变。
        before = (OutboundMessage("L2C_HeroUpdate", {"code": 10,
                      "heros": [encode_hero_data(h) for h in snapshot["heroes"]]}),)
        if self.equipment is not None:
            before += (OutboundMessage("L2C_EquipUpdate", {"code": 10,
                           "equip": self.equipment.values(player_id)["equip"]}),)
        before += (self.snapshot_push(player_id),)
        return OutboundMessage("L2C_UseEquipPlan", values, before_response=before)
