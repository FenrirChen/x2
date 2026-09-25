"""Read-only cross-index of the recovered client enum and the live server routes.

The curated feature list below records business coverage; enum presence alone
does not prove a UI path is currently reachable. Never opens the active save.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import tempfile

from x2server.player.battle import BattleService
from x2server.player.chat import SilentChatService
from x2server.player.economy import EconomyService
from x2server.player.equipment import EquipmentService
from x2server.player.lobby import LobbyService
from x2server.player.progression import ProgressionService
from x2server.player.store import PlayerStore
from x2server.player.wish import WishService
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY

ROOT = Path(__file__).resolve().parents[2]
DUMP = Path(r"D:\demo\x2\tools\Il2CppDumper-bin\dump.cs")
STATUS = {"COMPLETE", "PARTIAL", "STUB", "MISSING", "UNKNOWN", "INTENTIONALLY_UNSUPPORTED"}

# First match wins. Owner names inferred from request names are marked as such.
RULES = [
    ("T Chat / Comet / Snowflake", "ChatModule", r"Chat|Letter|Blog|Comet|Snowflake"),
    ("R Friend", "FriendModule", r"Friend|RecommendPlayer|SendFriend|ReceiveFriend|QueryPlayer|SetFriend"),
    ("S Club / Guild", "ClubModule", r"Club|RedPackage|Guild"),
    ("Q Mail", "MailModule", r"Mail|Attachment"),
    ("O Achievement", "AchievementModule", r"Achv|CollectionAward"),
    ("P Draw / Gacha", "DrawModule", r"Draw|CardPool"),
    ("N Shop", "ShopModule", r"Shop|Goods|Store|Recharge|Payment|GiftPackage"),
    ("F Equipment", "EquipModule", r"Equip|WashingRoom"),
    ("E Artifact", "ArtifactModule", r"Artifact|GodEqup|GodEquip|Jewel|GodSlot"),
    ("G Skill", "HeroModule", r"Skill|GodHole"),
    ("D Hero", "HeroModule", r"Hero|Fighter|Skin|Favor|Fetters|AIPoint|Date"),
    ("L DailyDungeon / Resource Dungeon", "ChapterModule", r"DailyDungeon|SecSweep|Sweep"),
    ("I Battle Runtime", "FightModule", r"FightDrop|FightKill|FightProfile|InsideBattle|RecordInsideBattle"),
    ("J Battle Checkout / Settlement", "ChapterModule", r"Checkout"),
    ("H Battle Entry", "ChapterModule", r"FightData|Prepare|BattleEnter|MatchEnter|BattleReady|Match|Team"),
    ("M Task", "DailyTaskModule", r"Task|TreasureBox|SignIn|TotalLogin"),
    ("K Mission / Chapter", "ChapterModule", r"Mission|Chapter|Story|SceneGlobal"),
    ("C Inventory / Item / Currency", "ItemModule", r"Item|Mobility|Power|Medal|Element"),
    ("A Bootstrap / Login / Session", "LoginModule", r"Login|ReConnect|Logout|ServerTableConfig|Account|SystemInfo|Certification|TelInfo|CDKey"),
    ("B Lobby / Navigation / Guide", "MainHallFSM", r"Guide|Novice|ButtonClick|EntryidStatus|Notic|Notice|Divination|GrowthBase|SharedMessage"),
    ("U Activity / Event", "ActivityModule", r"Activity|WorldBoss|Moon|BattlePass|Season|Lantern|Monopoly|NewYear|Happy|Tower|Race|Flip|Cafe|Alchemy|Explore|Train|Building|Yard|Light|ShuangHan|Dash|MiniGame|Invitation|Blood|Simple"),
]

def classify(name):
    short = name.removeprefix("C2L_")
    for domain, owner, pattern in RULES:
        if re.search(pattern, short, re.I):
            return domain, owner, "name_inference"
    # Every enum request gets a business-domain queue even when the exact
    # client Module cannot be attributed from the evidence at hand.
    if re.search(r"SelectRole|Appearance|Birthday|Contract|BlackNpc", short, re.I):
        domain = "D Hero"
    elif re.search(r"ExtraDrop", short, re.I):
        domain = "I Battle Runtime"
    elif re.search(r"DismissMember", short, re.I):
        domain = "S Club / Guild"
    elif re.search(r"PayBirthday", short, re.I):
        domain = "N Shop"
    elif re.search(r"Cheat|MissSyncData", short, re.I):
        domain = "A Bootstrap / Login / Session"
    elif re.search(r"Announcement|Questionnaire|Illustration", short, re.I):
        domain = "B Lobby / Navigation / Guide"
    else:
        domain = "U Activity / Event"
    return domain, "UNKNOWN", "weak_domain_inference"

def handlers():
    with tempfile.TemporaryDirectory(prefix="x2-coverage-") as temp:
        store = PlayerStore(Path(temp) / "audit.sqlite3")
        economy = EconomyService(store)
        services = [LobbyService(), economy, EquipmentService(store, economy), WishService(store, economy),
                    ProgressionService(store, economy), BattleService(store, economy), SilentChatService()]
        routes = {}
        for service in services:
            routes.update({name: type(service).__name__ + "." + method.__name__
                           for name, method in service.handlers().items()})
        routes.update({"C2L_HeroAll": "HeroService.query_all", "C2L_Login": "LoginService.login",
                       "C2L_ReConnect": "LoginService.reconnect", "C2L_ServerTableConfig": "LoginService.server_config"})
        store.close()
        return routes

STUB_ROUTES = {"C2L_GuideStep", "C2L_ButtonClick", "C2L_QueryActivity", "C2L_QueryWorldBossOpenTime",
    "C2L_QuerySimpleActivity", "C2L_QueryActivityDrawInfo", "C2L_QueryCollectionAward",
    "C2L_QueryDivination", "C2L_QueryReturnInfo", "C2L_QuerySharedMessage", "C2L_QueryGiftPackage",
    "C2L_QueryIllustrationData", "C2L_CheckFightProfile", "C2L_DelFightProfile", "C2L_MoonEquip",
    "C2L_CommercialShopGoods", "C2L_EntryidStatus", "C2L_QueryStarPrivilegeReward",
    "C2L_QueryStarPrivilegeInfo", "C2L_ReceiveGiftRew", "C2L_ShopGoods", "C2L_RefreshShop",
    "C2L_BuyGoods", "C2L_QueryGoodsInfo", "C2L_PickTreasureBox", "C2L_ChatJoin", "C2L_ChatAway"}
PARTIAL_ROUTES = {"C2L_Login", "C2L_ReConnect", "C2L_ServerTableConfig", "C2L_HeroAll", "C2L_HeroOpt",
    "C2L_UpHeroSkill", "C2L_Artifact", "C2L_EquipAll", "C2L_DoEquip", "C2L_DoUnEquip",
    "C2L_EquipStrengthen", "C2L_CardPool", "C2L_LuckDraw", "C2L_RequestDrawResult",
    "C2L_FightData", "C2L_FightDropData", "C2L_FightKillInfo", "C2L_CheckoutMainMissionSign",
    "C2L_GameTask", "C2L_DailyAndWeekTask", "C2L_FinishGameTask", "C2L_FinishGameTaskAsync",
    "C2L_ItemAll", "C2L_QueryMission", "C2L_SystemInfo"}

# Domain, subsystem, feature, request (or -), status, priority, static data,
# state mutation, persistence, login restore, refresh, covered, missing, evidence.
DETAILS = """
A Bootstrap / Login / Session|Bootstrap|controlInfo/connectInfo/address|-|PARTIAL|P0|partial|no|no|n/a|n/a|local route and MuMu bootstrap|address/new install/server variants|bootstrap/service.py; docs/phase13_first_contact.md
A Bootstrap / Login / Session|Identity|loginwithpw/httpLogin|-|PARTIAL|P0|partial|token|ephemeral|no|login|single revival account|multi-account/password reset/token restart|bootstrap/local_identity.py
A Bootstrap / Login / Session|Session|TCP login and identity|C2L_Login|PARTIAL|P0|partial|yes|SQLite player|partial|PlayerData|single account|multi-account/session restore|player/login.py
A Bootstrap / Login / Session|Session|reconnect/heartbeat/config|C2L_ReConnect|PARTIAL|P0|partial|session only|ephemeral|partial|L2C_ReConnect|same-process reconnect and empty heartbeat|process restart/replay of business deltas|player/login.py; network/connection.py
A Bootstrap / Login / Session|Login snapshot|full re-login state restoration|C2L_Login|PARTIAL|P0|partial|read|partial|partial|L2C_Login plus PlayerData|hero/equip/item/daily/weekly/draw|guide/activity/mail/mission variants|player/login.py:39
B Lobby / Navigation / Guide|MainHallFSM|lobby init and UI stack|-|PARTIAL|P0|partial|no|no|partial|query pushes|normal lobby open|all module returns/stack and error branches|dump.cs MainHallFSM; player/lobby.py
B Lobby / Navigation / Guide|Guide|GuideStep/Tito persistence|C2L_GuideStep|MISSING|P0|partial|no|no|no|none|tutorial skip compatible|guide flags and progression|player/lobby.py; dump.cs TitoGuideModule
B Lobby / Navigation / Guide|Navigation|ButtonClick/module opening|C2L_ButtonClick|STUB|P0|partial|no|no|no|ack only|button ack|unlock and navigation state|player/lobby.py:52
B Lobby / Navigation / Guide|First entry|newbie skip/initial Chapter|-|PARTIAL|P0|partial|snapshot|SQLite|yes|PlayerData|valid chapter/section seed|all first entry and guide paths|SESSION_HANDOFF.md
C Inventory / Item / Currency|Inventory|stackable ItemAll/ItemUpdate|C2L_ItemAll|PARTIAL|P1|partial|yes|inventory table|yes|ItemUpdate|materials/currency projection|all 3026 item types/time-limited/locks|player/economy.py
C Inventory / Item / Currency|Currency|fixed grant/consume/negative balance|-|PARTIAL|P1|partial|yes|SQLite transaction|yes|PlayerData/ItemUpdate|known currency destinations|special currency/instance types|player/economy.py:18
C Inventory / Item / Currency|Instances|instance item reward destination|-|PARTIAL|P1|partial|deferred|pending_rewards|no|no|test equipment instance seed|real generic instances and pending delivery|player/economy.py:288
C Inventory / Item / Currency|Item operations|lock/reclaim/compose|C2L_ItemOpt|MISSING|P1|partial|no|no|no|none|none|item operation variants|dump.cs ERequestTypes
D Hero|Hero query|HeroAll/show/selection|C2L_HeroAll|PARTIAL|P1|partial|show only|snapshot|yes|HeroAll/HeroUpdate|owned heroes|selection and other query entry points|player/hero.py; player/login.py
D Hero|Unlock|fragment synthesis|C2L_HeroOpt|PARTIAL|P1|partial|yes|snapshot+inventory|yes|HeroUpdate/ItemUpdate|39 open hero prototypes|other unlock conditions/hero types|player/progression.py
D Hero|Growth|level/star|C2L_HeroOpt|PARTIAL|P1|partial|yes|snapshot+inventory|yes|HeroUpdate/PlayerData|static costs and 1003 tested|full hero attribute and UI variants|player/progression.py
D Hero|Properties|attribute refresh|-|PARTIAL|P1|partial|derived|not stored|derived|HeroUpdate|battle 39 static bases|equip/artifact/set/skill full aggregation|player/progression.py; player/battle.py
E Artifact|Unlock|initial weapon unlock|C2L_Artifact|PARTIAL|P1|partial|yes|snapshot|yes|HeroUpdate|39 prototypes|all hero live UI|player/progression.py
E Artifact|Growth|level up/fuse/costs|C2L_Artifact|PARTIAL|P1|partial|yes|snapshot+inventory|yes|HeroUpdate/ItemUpdate|rank curve and material consume|complete attributes/fuse UI variants|player/progression.py
E Artifact|Jewel|socket/replace/remove|C2L_Artifact|PARTIAL|P1|partial|yes|snapshot+inventory|yes|HeroUpdate/ItemUpdate|request socket raw ID|socket unlock/attribute aggregation/live UI|player/progression.py; player/hero.py
E Artifact|Other jewel|compose/god slot lock|C2L_JewelCompose|MISSING|P1|partial|no|no|no|none|none|compose/god slot|dump.cs ERequestTypes
F Equipment|Bag|equipment instances/list|C2L_EquipAll|PARTIAL|P1|partial|yes|equipment_instances|yes|EquipAll|seeded instances|generic drops/duplicates/lock|player/equipment.py
F Equipment|Wear|equip/unequip/replace|C2L_DoEquip|PARTIAL|P1|partial|yes|snapshot|yes|HeroUpdate/EquipUpdate|six positions and replacement|all slot/client live variants|player/equipment.py
F Equipment|Enhance|experience/gold/random +3|C2L_EquipStrengthen|PARTIAL|P1|partial|yes|equipment_instances|yes|EquipUpdate/PlayerData|exp currency and random property step|fodder and all star/quality branches|player/equipment.py
F Equipment|Other|lock/reclaim/set/loadout|C2L_LockEquip|MISSING|P1|partial|no|no|no|none|none|lock/reclaim/loadout|dump.cs ERequestTypes
G Skill|List|hero skill list|-|PARTIAL|P1|partial|snapshot|snapshot|yes|HeroAll/HeroUpdate|initial skill IDs|special GodHole and complete unlock|player/hero.py
G Skill|Growth|skill level/material/prerequisite|C2L_UpHeroSkill|PARTIAL|P1|partial|yes|snapshot+inventory|yes|HeroUpdate/ItemUpdate|1003 single step|other 38 heroes/bulk/special|player/progression.py:203
G Skill|Special|StarSkill/GodHole|C2L_StarSkillUp|MISSING|P1|partial|no|no|no|none|none|special skill variants|dump.cs ERequestTypes
H Battle Entry|Main|ordinary MainMission FightData|C2L_FightData|PARTIAL|P0|partial|yes|battle_entries/economy_runs typed metadata|partial|FightData/PlayerData|78 of 79 normal sections and up to 3 owned heroes|remaining normal section/full unlock/profile semantics|player/battle.py; player/battle_entry.py
H Battle Entry|Other|resource/daily entry|C2L_FightData|PARTIAL|P0|partial|yes|battle_entries/economy_runs typed metadata|partial|FightData/PlayerData|20 linked E_Daily sections with fixed plus per-section Revival drop x1, static stamina and compat schedule|121 linked blocked sections/6 orphan E_Daily/official calendar/attempts|player/battle_entry.py; daily_dungeon_reward_audit.json
H Battle Entry|Other|challenge/endless/special entry|C2L_FightData|MISSING|P0|partial|no|no|no|none|none|challenge/endless/weekly/story experience|SectionTable EType
H Battle Entry|Other|activity/event battle entry|C2L_FightData|MISSING|P1|partial|no|no|no|none|none|activity battle/wave/boss/tower/monopoly|SectionTable EType
H Battle Entry|Flow|retry/next stage/prepare/formation|C2L_PrepareMainMission|PARTIAL|P0|partial|limited|typed battle entries|partial|FightData|3 owned heroes, replay cache, duplicate active rejection, old-run refund|prepare/profile resume/next source and forced formation|player/battle.py; registry.py
H Battle Entry|Flow|sweep|C2L_SecSweep|MISSING|P1|partial|no|no|no|none|none|sweep all section variants|dump.cs ChapterModule.SweepSection
I Battle Runtime|Run|UUID/sign/session/disconnect|C2L_FightData|PARTIAL|P0|partial|yes|battle_entries/economy_runs typed metadata|partial|FightData|UUID, type/source/map/team and bounded 1h latest run|resume/profile/reconnect/multiple runs|player/battle.py
I Battle Runtime|Drop|FightDropData/DropValues|C2L_FightDropData|STUB|P1|missing|no|no|no|empty response|empty compatible list|random/monster drop calculation|player/battle.py:129; economy_missing_evidence_followup.md
I Battle Runtime|Telemetry|FightKillInfo|C2L_FightKillInfo|STUB|P1|partial|no|no|no|ack|request accepted|verified kill task events|player/battle.py:48
I Battle Runtime|Profile|disconnect/abandon/retry profile|C2L_CheckFightProfile|STUB|P0|partial|no|no|no|empty profile|absent profile ack|resumable battle state|player/lobby.py:53; player/battle.py:141
J Battle Checkout / Settlement|Receipt|signed checkout/idempotency|C2L_CheckoutMainMissionSign|PARTIAL|P0|partial|yes|battle_receipts|partial|CheckoutMainMission|same run duplicate/conflict|official sign/replay/variant checkout|player/battle.py
J Battle Checkout / Settlement|Rewards|first clear/normal fixed gift|-|PARTIAL|P0|complete|yes|economy_grants/clears|partial|ItemUpdate/PlayerData|78 Main sections and deterministic Daily fixed groups|other SectionTypes/random Gift groups/instance destinations|player/economy.py; client_economy_data_audit.md
J Battle Checkout / Settlement|Rewards|random/monster/sweep rewards|-|MISSING|P1|missing|no|no|no|none|none|DropValueID chain/sweep rewards|economy_missing_evidence_followup.md
J Battle Checkout / Settlement|Progress|XP/task/next unlock|-|PARTIAL|P0|partial|yes|snapshot/tasks|partial|PlayerData/TaskUpdate|main section advance and clear event|other chapter/section types|player/economy.py:295
K Mission / Chapter|Query|mission/chapter/story list|C2L_QueryMission|PARTIAL|P0|partial|read|clears|partial|L2C_QueryMission|mainMission clear list and Daily OtherChapter frontier|other SectionTypes/story/chest/star|player/economy.py; ChapterModule.OnHandleQueryMission
K Mission / Chapter|Progress|current chapter/section and next unlock|-|PARTIAL|P0|partial|yes|snapshot+clears|yes|PlayerData|78 ordered sections|section prerequisite/branch/chapter complete|player/economy.py:300
K Mission / Chapter|Rewards|chapter chest/star/story trigger|-|MISSING|P1|partial|no|no|no|none|none|ChapterInfo and GetCollectionAward|client_economy_data_audit.md
L DailyDungeon / Resource Dungeon|List|25 dungeons/available sections|-|PARTIAL|P0|complete|static client config|battle_entry_catalog|yes|client local table|25 indexed dungeon rows and 176 links|official server availability/attempt state|battle_entry_catalog.json; live request trace
L DailyDungeon / Resource Dungeon|Entry|stamina/attempts/unlock/reset|C2L_FightData|PARTIAL|P0|partial|yes|battle_entries/economy_runs/battle_costs|yes|FightData/PlayerData|20 linked daily sections with fixed plus per-section Revival drop x1, static ManualValue and ordered unlock|121 reward-blocked linked/6 orphan/official weekday and attempts|player/battle_entry.py; daily_dungeon_reward_audit.json
L DailyDungeon / Resource Dungeon|Settlement|fixed/random reward/attempt count|-|PARTIAL|P0|partial|yes|economy_grants/clears/battle_receipts|yes|RewardData/ItemUpdate/PlayerData/QueryMission|first and normal Gift including static E_Random, per-section Revival drop x1 for 20 rows, first-clear record, Daily frontier|official DropValue quantity/probability, multi-preview/instance destinations/attempts|player/economy.py; daily_dungeon_reward_audit.json
L DailyDungeon / Resource Dungeon|Sweep|MopReward/limit|C2L_SecSweep|MISSING|P1|complete|no|no|no|none|none|MopReward 41 sections|client_economy_data_audit.md
M Task|List|daily/weekly instance/period|C2L_GameTask|PARTIAL|P1|complete|yes|economy_tasks/periods|yes|TaskUpdate|40 static tasks and user calendar|challenge/event tasks|player/economy.py
M Task|Events|battle/stamina/growth/online progress|-|PARTIAL|P1|complete|yes|economy_events|yes|TaskUpdate|clear/level/equip/time/login|kill/social/explore/alchemy/etc|player/economy.py
M Task|Claim|fixed reward/idempotency|C2L_FinishGameTask|PARTIAL|P1|complete|yes|economy_grants/tasks|yes|ItemUpdate/TaskUpdate|daily/weekly fixed gifts|activity/challenge rewards|player/economy.py
M Task|Activity|activity point boxes|C2L_PickTreasureBox|STUB|P1|complete|no|no|no|reject|none|daily/weekly box list/status/claim|player/economy.py:385
M Task|Reset|daily 00/week Mon05|-|PARTIAL|P1|partial|yes|periods/history|yes|TaskUpdate|defined Revival calendar|all task families/edge cases|player/task_calendar.py
N Shop|Goods|shop list/goods/query|C2L_ShopGoods|STUB|P1|partial|no|no|no|reject|safe error instead of crash|25 shops/1567 group rows/item and quantity missing|player/economy.py; economy_missing_evidence_followup.md
N Shop|Purchase|buy/price/limit|C2L_BuyGoods|STUB|P1|partial|no|no|no|reject|none|all goods and purchase state|player/economy.py
N Shop|Refresh|refresh/cost/reset|C2L_RefreshShop|STUB|P1|partial|no|no|no|reject|none|refresh inventory and limits|player/economy.py
O Achievement|List|overview/detail/progress|C2L_AchvOverView|MISSING|P2|partial|no|no|no|none|none|318 static achievements|client_economy_data_audit.md; dump.cs AchievementModule
O Achievement|Claim|achievement reward|C2L_AchvReward|MISSING|P2|partial|no|no|no|none|none|reward/point rewards|dump.cs ERequestTypes
P Draw / Gacha|Pools|pool config/rotation/cost|C2L_CardPool|PARTIAL|P2|partial|yes|wish_state|yes|CardPool|30 up/3 limited/10 jewel|all 48 DrawParam/client artwork/live timing|player/wish.py
P Draw / Gacha|Draw|single/ten/result/pity|C2L_LuckDraw|PARTIAL|P2|partial|yes|wish_receipts/pity/inventory|yes|LuckDraw/ItemUpdate|known 43 rotating pools|remaining pool/odds and UI variants|player/wish.py
Q Mail|Inbox|list/read/delete|C2L_MailData|MISSING|P2|unknown|no|no|no|none|none|read/delete/all variants|dump.cs MailModule
Q Mail|Attachment|claim/all|C2L_ReceiveAttachment|MISSING|P2|unknown|no|no|no|none|none|claim once/attachment persistence|dump.cs ERequestTypes
R Friend|Social|list/apply/accept/delete|C2L_UpdateFriends|MISSING|P3|unknown|no|no|no|none|none|all friend requests|dump.cs FriendModule
R Friend|Gifts|stamina/friend coin/tasks|C2L_SendFriendCoin|MISSING|P3|partial|no|no|no|none|none|friend gifting and task events|dump.cs FriendModule
S Club / Guild|Club|create/join/member/donate|C2L_CreateClub|MISSING|P3|unknown|no|no|no|none|none|club lifecycle and privilege|dump.cs ClubModule
S Club / Guild|Club events|guild challenge/reward|C2L_ClubActiMainData|MISSING|P3|partial|no|no|no|none|none|guild battles and rewards|dump.cs ClubModule
T Chat / Comet / Snowflake|Compat|Null Chat transport/join|C2L_ChatJoin|STUB|P3|partial|no|no|no|ack|chat node and socket silence|full chat content|player/chat.py; SESSION_HANDOFF.md
T Chat / Comet / Snowflake|Full chat|content/private/comet|C2L_ChatEvent|INTENTIONALLY_UNSUPPORTED|P3|unknown|no|no|no|none|none|full social service intentionally outside Null Chat target|SESSION_HANDOFF.md Phase18
U Activity / Event|Catalog|activity list/open conditions|C2L_QueryActivity|STUB|P2|partial|no|no|no|empty|none|active content/conditions|player/lobby.py; dump.cs ActivityModule
U Activity / Event|Tasks|activity task/shop/reward|C2L_ActivityMissionData|MISSING|P2|partial|no|no|no|none|none|314 ActivityTask/693 ActivityBoxGoods|client_economy_data_audit.md
U Activity / Event|Battle|activity battle/tower/boss|C2L_FightData|MISSING|P2|partial|no|no|no|none|none|event Section types|SectionTable EType
U Activity / Event|Ended events|season/battlepass/New Year/monopoly|C2L_QueryBattlePassInfo|UNKNOWN|P3|partial|no|no|no|none|none|operational value and schedule not decided|dump.cs activity modules
V Tutorial / Guide|Tutorial|skip flags/newbie finish/GuideStep163|C2L_NoviceFinish|MISSING|P0|partial|no|no|no|none|skip to valid chapter|guide state/feature unlock consistency|SESSION_HANDOFF.md; dump.cs TitoGuideModule
W Growth / Progression|Account|player level curve/gifts/function open|-|PARTIAL|P1|partial|yes|snapshot|partial|PlayerData|RoleExp curve and advancement|terminal overflow/level gift timing/function gates|client_progression_data_audit.md
W Growth / Progression|Cross-system|hero/artifact/equipment/skill aggregation|-|PARTIAL|P1|partial|derived|mixed|partial|HeroUpdate|some costs and transitions|full stat pipeline and special skills|client_progression_data_audit.md
""".strip().splitlines()

def main():
    text = DUMP.read_text(encoding="utf-8", errors="replace")
    enum = text[text.index("public enum ERequestTypes"):]
    enum = enum[:enum.index("\n}")]
    pairs = [(name, int(number)) for name, number in re.findall(
        r"public const ERequestTypes E(C2L_\w+) = (\d+);", enum)]
    id_by_name = dict(re.findall(r"public const ERequestTypes E((?:C2L|L2C)_\w+) = (\d+);", enum))
    id_by_name = {k: int(v) for k, v in id_by_name.items()}
    routes = handlers()
    registered = {e.name for e in CORE_MESSAGE_REGISTRY._by_name.values() if e.name.startswith("C2L_")}
    requests = []
    for name, request_id in pairs:
        domain, owner, owner_evidence = classify(name)
        response = "L2C_" + name[4:]
        if name == "C2L_CheckoutMainMissionSign":
            response = "L2C_CheckoutMainMission"
        route = routes.get(name)
        stub = (name in STUB_ROUTES or route is not None and
                (route.startswith("LobbyService.") and name != "C2L_SystemInfo" or
                 route in {"BattleService.drop_data", "BattleService.kill_info"}))
        state = "STUB" if stub else "PARTIAL" if route else "UNKNOWN" if owner == "UNKNOWN" else "MISSING"
        requests.append({"request_id": request_id, "request_type": name,
            "response_id": id_by_name.get(response), "response_type": response if response in id_by_name else None,
            "domain": domain, "client_module": owner, "owner_evidence": owner_evidence,
            "protobuf_class_in_dump": bool(re.search(r"public class " + re.escape(name) + r"\s*:", text)),
            "server_registry": name in registered, "server_handler": route,
            "status": state})
    details = []
    for line in DETAILS:
        domain, subsystem, feature, request, status, priority, static, mutation, persist, login, refresh, covered, missing, evidence = line.split("|", 13)
        assert status in STATUS and priority in {"P0", "P1", "P2", "P3"}
        domain_request = next((r for r in requests if r["request_type"] == request), None)
        details.append({"domain": domain, "subsystem": subsystem, "feature": feature,
            "client_module": domain_request["client_module"] if domain_request else classify(request)[1] if request != "-" else domain.split(" ", 1)[-1],
            "client_entry": request if request != "-" else "static/module path",
            "request_id": domain_request["request_id"] if domain_request else None,
            "request_type": request if request != "-" else None,
            "response_id": domain_request["response_id"] if domain_request else None,
            "response_type": domain_request["response_type"] if domain_request else None,
            "server_handler": domain_request["server_handler"] if domain_request else None,
            "static_data_status": static, "runtime_logic_status": status,
            "state_mutation": mutation, "persistence": persist, "login_restore": login,
            "client_refresh": refresh, "known_variants": covered + "; " + missing,
            "covered_variants": covered, "missing_variants": missing,
            "status": status, "evidence": evidence, "blocker": "BLOCKED_BY_MISSING_DATA" if
                ("random" in missing.lower() or domain.startswith("N Shop")) else None,
            "priority": priority, "notes": "Enum presence does not establish reachable UI; runtime probe if needed."})
    # Request inventory is deliberately separate from business feature counts.
    counts = Counter(f["status"] for f in details)
    result = {"audit_date": datetime.now(timezone.utc).isoformat(),
        "scope": "read-only client-enum-to-runtime cross audit; no APK rescan or active save writes",
        "sources": [str(DUMP), "src/x2server/protocol/registry.py", "tools/local_game_server.py",
                    "src/x2server/player", "src/x2server/messages", "docs/client_economy_data_audit.md",
                    "docs/client_progression_data_audit.md", "D:/demo/x2/SESSION_HANDOFF.md"],
        "summary": {"total_domains": len({f["domain"] for f in details}), "total_features": len(details),
            "feature_status_counts": dict(counts), "client_requests_total": len(requests),
            "server_handlers_total": len(routes), "registered_client_requests": len(registered),
            "unhandled_client_requests": sum(r["server_handler"] is None for r in requests),
            "unknown_owner_requests": sum(r["client_module"] == "UNKNOWN" for r in requests)},
        "features": details, "client_requests": requests,
        "domain_request_counts": dict(Counter(r["domain"] for r in requests))}
    output = ROOT / "analysis/coverage/runtime_coverage.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    print("unknown owner examples", [r["request_type"] for r in requests if r["client_module"] == "UNKNOWN"][:30])

if __name__ == "__main__":
    main()
