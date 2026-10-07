"""兽主套装预设 (EquipPlan) 的线格式，取自 2.4 客户端自身类型。

客户端把预设挂在 PlayerData 的第 9 号成员上（PlayerData 里 EquipPlan 紧跟
StarMap 之后），结构链条是：

    PlayerData.EquipPlan : EquipPlanProto        { List<ContainerIntPlanProto> Plan }
    ContainerIntPlanProto                        { int32 idx; PlanProto val }
    PlanProto                                    { string Name; int32 SetTopTime;
                                                   List<ContainerIntIntProto> Position }

客户端侧对应的运行时类型是 `EquipPlan { List<PlayerDbData.Plan> Plan }`、
`Plan { string Name; int SetTopTime; Dictionary<int,int> Position }`，字段顺序与
上面的 proto 类一致，因此 Position 的键值对沿用项目里既有的
KeyValuePair<int32,int32> 形状 (key=1,value=2)。

注意 ContainerIntPlanProto 只写 idx、不写 val 是一条“已删除墓碑”：客户端的
PlayerData 合并是按 idx 建字典的（PlayerDbDataMerge.Merge），所以删除一个预设
必须把它的 id 继续下发一次（val 缺席）才能让客户端把本地那条抹掉。

请求/回包各四对，消息号 423..430（见 protocol/registry.py 的 EQUIP_PLAN_IDS）。
"""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

# ContainerIntIntProto: (slot, equipId)。slot 与 HeroData.equips 里的 position 同义
# （0 基的槽位号），equipId 是 equipment_instances.id。
PLAN_POS = S("ContainerIntIntProto", (
    F(1, "Key", K.INT32), F(2, "Value", K.INT32)))
# PlanProto: 名字 / 置顶时间 / 槽位 -> 装备。
PLAN = S("PlanProto", (
    F(1, "Name", K.STRING), F(2, "SetTopTime", K.INT32),
    F(3, "Position", K.MESSAGE, repeated=True)))
# ContainerIntPlanProto: 1 = 预设 id, 2 = PlanProto（只写 1 即删除墓碑）。
PLAN_ENTRY = S("ContainerIntPlanProto", (
    F(1, "Key", K.INT32), F(2, "Val", K.MESSAGE)))
# PlayerDataProto 的第 9 号成员。
EQUIP_PLAN = S("EquipPlanProto", (F(1, "Plan", K.MESSAGE, repeated=True),))

EQUIP_PLAN_SCHEMAS = {
    "C2L_UpdateEquipPlan": S("C2L_UpdateEquipPlan", (
        F(1, "planId", K.INT32), F(2, "name", K.STRING),
        F(3, "pos", K.MESSAGE, repeated=True))),
    "L2C_UpdateEquipPlan": S("L2C_UpdateEquipPlan", (
        F(1, "code", K.ENUM), F(2, "planId", K.INT32))),
    "C2L_SetTopEquipPlan": S("C2L_SetTopEquipPlan", (
        F(1, "planId", K.INT32), F(2, "isTop", K.BOOL))),
    "L2C_SetTopEquipPlan": S("L2C_SetTopEquipPlan", (
        F(1, "code", K.ENUM), F(2, "planId", K.INT32))),
    "C2L_DelEquipPlan": S("C2L_DelEquipPlan", (F(1, "planId", K.INT32),)),
    "L2C_DelEquipPlan": S("L2C_DelEquipPlan", (
        F(1, "code", K.ENUM), F(2, "planId", K.INT32))),
    "C2L_UseEquipPlan": S("C2L_UseEquipPlan", (
        F(1, "planId", K.INT32), F(2, "heroId", K.INT32))),
    "L2C_UseEquipPlan": S("L2C_UseEquipPlan", (
        F(1, "code", K.ENUM), F(2, "planId", K.INT32), F(3, "heroId", K.INT32))),
}
EQUIP_PLAN_IDS = tuple(zip(EQUIP_PLAN_SCHEMAS, (423, 424, 425, 426, 427, 428, 429, 430)))
