"""约会 / 契约 (FavorDate) protocol: the four exchanges the 2.4 client fires.

The 2.4 client still ships the whole 约会 page under ``FavorDateModule``; the
data was switched off, not the code (``FavorabilityDate`` is 100 rows of
``IsUse=2``, and player/date.py's catalog turns two rows per hero back on). The
exchanges below were already named by the recovered id table but nothing on the
server answered them - an unanswered *known* id is worse than an unknown one:
the dispatcher sends nothing back and the page waits forever.

Field names and declaration order come from the client's own types:

    C2L_QueryHeroDate     { heroId }
    L2C_QueryHeroDate     { code, List<NpcDate> date, List<int> journal,
                            int skin, int heroId }
    C2L_UnLockDateOption  { heroId, dateId, optionId }
    L2C_UnLockDateOption  { code, heroId, dateId, KeyValuePair<int,int> option }
    C2L_SelcetDateOption  { heroId, dateId, optionEffectId }
    L2C_SelcetDateOption  { code, heroId, dateId, List<KeyValuePair<int,int>> option }
    C2L_OpenContract      { heroId }
    L2C_OpenContract      { code, heroId, RewardData rewardData }

``NpcDate`` is a client class too (status / option / id); its ``option`` pairs are
what the client counts as 契约碎片, see player/date.py. A LOCK date must carry no
zero-value chip: the red dot counts zeros over all dates without a status gate,
while MarryView only binds chips of an UNLOCK date, so those zeros would be a dot
with nothing to tap.

``status`` is DateStatus (0 NONE, 1 NOTOPEN, 2 LOCK, 3 UNLOCK).
"""
from x2server.protocol.protobuf import FieldKind as K, ProtoField as F, ProtoSchema
# NpcDate.option elements are the same KeyValuePair_Int32_Int32 lobby already
# declares (activity reward pools and medal display use it too), so it is not
# registered a second time under the same name.
from x2server.messages.lobby import MISSION_PAIR as KEY_VALUE

# EC2L_*/EL2C_* pairs this module owns, kept next to the schemas they describe.
DATE_IDS = (
    ("QueryHeroDate", 641, 642),
    ("UnLockDateOption", 645, 646),
    ("SelcetDateOption", 647, 648),
    ("OpenContract", 649, 650),
)

# DateStatus, from the client's own enum (0-based).
DATE_STATUS_NONE = 0
DATE_STATUS_NOT_OPEN = 1
DATE_STATUS_LOCK = 2
DATE_STATUS_UNLOCK = 3

# One (Key -> value) pair. ``Key`` is the 碎片's **拼图位置** (1..18), *not* the
# OptionEffect id: the client indexes its 6x3 chip grid with ``nodes[Key - 1]``
# and builds the sprite name as ``前缀 + Key``, so an effect id would both throw
# and paint the wrong fragment. ``Value`` is 0 while it is locked and 1 once the
# date handed it out. KEY_VALUE is KeyValuePair_Int32_Int32, imported above.
NPC_DATE = ProtoSchema("NpcDate", (
    F(1, "status", K.INT32),
    F(2, "option", K.MESSAGE, repeated=True),
    F(3, "id", K.INT32),
))

DATE_SCHEMAS = {
    "C2L_QueryHeroDate": ProtoSchema("C2L_QueryHeroDate", (
        F(1, "heroId", K.INT32),
    )),
    "L2C_QueryHeroDate": ProtoSchema("L2C_QueryHeroDate", (
        F(1, "code", K.ENUM),
        F(2, "date", K.MESSAGE, repeated=True),
        F(3, "journal", K.INT32, repeated=True),
        F(4, "skin", K.INT32),
        F(5, "heroId", K.INT32),
    )),
    "C2L_UnLockDateOption": ProtoSchema("C2L_UnLockDateOption", (
        F(1, "heroId", K.INT32),
        F(2, "dateId", K.INT32),
        F(3, "optionId", K.INT32),
    )),
    # The reply carries the *one* pair that changed. The client looks it up by key
    # in the date's current option list and writes the reply's value over it
    # (FavorDateModule_OnHandleUnlockChip) - it never appends a pair, so every
    # chip has to already be in the list the query reply handed out.
    "L2C_UnLockDateOption": ProtoSchema("L2C_UnLockDateOption", (
        F(1, "code", K.ENUM),
        F(2, "heroId", K.INT32),
        F(3, "dateId", K.INT32),
        F(4, "option", K.MESSAGE),
    )),
    "C2L_SelcetDateOption": ProtoSchema("C2L_SelcetDateOption", (
        F(1, "heroId", K.INT32),
        F(2, "dateId", K.INT32),
        F(3, "optionEffectId", K.INT32),
    )),
    # A *whole-list* reply: FavorDateModule_OnHandleSelectDateOption replaces the
    # date's option list with this one, so it must carry the chips too - sending
    # only the chosen option would zero the 碎片 count for that date.
    "L2C_SelcetDateOption": ProtoSchema("L2C_SelcetDateOption", (
        F(1, "code", K.ENUM),
        F(2, "heroId", K.INT32),
        F(3, "dateId", K.INT32),
        F(4, "option", K.MESSAGE, repeated=True),
    )),
    "C2L_OpenContract": ProtoSchema("C2L_OpenContract", (
        F(1, "heroId", K.INT32),
    )),
    "L2C_OpenContract": ProtoSchema("L2C_OpenContract", (
        F(1, "code", K.ENUM),
        F(2, "heroId", K.INT32),
        F(3, "rewardData", K.MESSAGE),
    )),
    "NpcDate": NPC_DATE,
}
