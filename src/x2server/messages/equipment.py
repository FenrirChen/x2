"""Client 2.4 HeroEquip instance and EquipAll wire shapes."""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema as S

EQUIP_PARAM = S("EquipParam", tuple(F(2 * index - 1, f"at{index}", K.INT32)
    for index in range(1, 7)) + tuple(F(2 * index, f"av{index}", K.INT32)
    for index in range(1, 7)) + tuple(F(12 + index, f"lock{index}", K.INT32)
    for index in range(1, 7)))
HERO_EQUIP = S("HeroEquip", (
    F(1, "id", K.INT32), F(2, "typeId", K.INT32), F(3, "level", K.INT32),
    F(4, "exp", K.INT32), F(5, "star", K.INT32), F(6, "status", K.INT32),
    F(7, "param", K.MESSAGE), F(8, "lockState", K.INT32),
    F(9, "timeSec", K.INT32), F(10, "seasonId", K.INT32)))
EQUIPMENT_SCHEMAS = {s.name: s for s in (
    S("C2L_EquipStrengthen", (F(1, "equipID", K.INT32),)),
    S("L2C_EquipStrengthen", (F(1, "code", K.ENUM), F(2, "equipID", K.INT32), F(3, "level", K.INT32))),
    S("C2L_DoEquip", (F(1, "equipID", K.INT32), F(2, "heroID", K.INT32), F(3, "optType", K.ENUM))),
    S("L2C_DoEquip", (F(1, "code", K.ENUM), F(2, "equipID", K.INT32), F(3, "heroID", K.INT32))),
    S("C2L_DoUnEquip", (F(1, "posIdx", K.INT32), F(2, "heroID", K.INT32), F(3, "optType", K.ENUM))),
    S("L2C_DoUnEquip", (F(1, "code", K.ENUM), F(2, "posIdx", K.INT32), F(3, "heroID", K.INT32))),
    S("L2C_EquipUpdate", (F(1, "code", K.ENUM), F(2, "equip", K.MESSAGE, repeated=True))),
    S("C2L_EquipReclaim", (F(1, "equipID", K.INT32, repeated=True),)),
    S("L2C_EquipReclaim", (F(1, "code", K.ENUM), F(2, "rewardData", K.MESSAGE))),
    S("L2C_EquipRemove", (F(1, "ids", K.INT32, repeated=True),)),
    # 兽主锁定 (883/884). The client's own wire class is C2L_LockEquip{equipID} ->
    # L2C_LockEquip{code, HeroEquip} (BagModule.SendLockEquipRequest /
    # OnReceiveLockedEquipMsg). The request carries only the id, so the server toggles
    # HeroEquip.lockState (field 8) and echoes the updated instance back.
    S("C2L_LockEquip", (F(1, "equipID", K.INT32),)),
    S("L2C_LockEquip", (F(1, "code", K.ENUM), F(2, "heroEquip", K.MESSAGE))),
)}
