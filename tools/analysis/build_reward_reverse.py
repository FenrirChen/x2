"""Consolidate this round's reverse-engineering evidence into analysis/reward_reverse/*.json."""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "reward_reverse"
OUT.mkdir(parents=True, exist_ok=True)

W = lambda name, obj: (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

# ---------- 1. fightitembag_methods.json ----------
W("fightitembag_methods.json", {
 "class": "LogicX2.FightItemBag (TypeDefIndex 5185)",
 "fields": {
   "mItemList": "FightItemData[] (0x10) — battle item slots; FightItemData{id,num,quality,source:ItemSource,isFirstGet}",
   "mMoney": "Dictionary<int,SmartInt> (0x18) — in-battle currency buckets (901/903/907…); NOT account gold",
   "mTrueMoney": "Dictionary<int,SmartInt> (0x20) — 'true currency' bucket (GetTrueCurrency default 901)",
   "RelicItem": "List<int> (0x30) — roguelite relic ids (local only)",
   "TowerItem": "List<int> (0x38) — tower-mode items (local only)",
   "TowerLib": "List<int> (0x40) — tower library",
   "ConsumeSilver": "int (0x48) — silver(903) spent counter",
   "PickupSilver": "int (0x4C) — silver(903) picked counter",
   "GainRate": "float (0x58) — drop gain rate buff",
   "CostRate": "float (0x5C) — cost rate buff",
   "profileDropItems": "List<ProfileDropItem> (0x60) — telemetry snapshot for C2L_FightDropData",
   "moneyGet": "GetMoneyInGame (0x68)",
   "mItemDayNumCache": "Dictionary<int,int> (0x98, on DropItemManager) — per-item daily drop counts for Item.DropLimit"
 },
 "key_methods": {
   "AddItem(id,quality,num,silverCount,show,recover,source=1)": {"rva": "0x1E46DAC",
     "notes": "source default = ItemSource.FIGHT(1); routes 901/903/907-type ids into money buckets (constants 0x385/0x387/0x38B); real items into mItemList"},
   "AddGold(num, itemID=903)": {"rva": "0x1E526CC",
     "callers": ["LogicBattle.OnCreatTowerUnit/OnDestroyTowerUnit/OnUpdateTowerUnit/RecoverBattleData",
                  "TowerDefenseSpawner.BeginSpawn","Unit.CheckHPSubRes x2","Unit.UseSkill",
                  "TowerDefenseModuleNeo.AddTowerMaxNum","TriggerActions.SilverOpera"],
     "notes": "writes mMoney[itemID] only; NO account conversion inside"},
   "AddTrueCurrency(CurrencyID,num)": {"rva": "0x1E52574"},
   "GetTrueCurrency(ID=901)": {"rva": "0x1E516B4"},
   "GetCurrentItems()": {"rva": "0x1E51784", "returns": "List<ProfileDropItem> — full bag telemetry for C2L_FightDropData"},
   "GetPersistentItemsList()": {"rva": "0x1E51A54",
     "pseudocode": [
       "result = new List<ItemDataP>()",
       "bag = LogicBattle.Current.FightItemBag",
       "foreach (FightItemData it in bag.mItemList):",
       "    if it == null: continue",
       "    info = ItemManager.GetItem(it.ID)",
       "    if info == null: continue",
       "    if (int)info.ItemUseScence != 1 /*E_Outside*/: continue",
       "    result.Add(new ItemDataP{ id=it.ID, num=it.Num, quality=it.Quality })  // eNum left 0",
       "_ = Gold;  // dead read, return value discarded (0x1E51C18 restores list pointer)",
       "return result"],
     "note": "no source==FIGHT filter here, no maze branch; the authoritative checkout filter is SetCheckout_BattleItem"},
   "Clear()/DeleteItemByIndex/UseItemByID": "battle-local lifetime only"
 }})

# ---------- 2. item_use_scene_consumers.json ----------
W("item_use_scene_consumers.json", {
 "enum ItemEItemUseScence": {"E_Maze": 0, "E_Outside": 1, "E_Alchemy": 2},
 "item_table_distribution": {"E_Outside": 2261, "E_Alchemy": 81, "unset": 684},
 "consumers": [
   {"method": "FightModule.SetCheckout_BattleItem", "rva": "0x1442894",
    "reads": "Item.ItemUseScence @ +0x20 (0x1442AB0)",
    "semantics": "checkout filter: source==ItemSource.FIGHT(1) required (0x1442AA4); "
                 "E_Outside(1) -> C2L_CheckoutMainMission.outsideItems; E_Maze(0) -> mazeItems with "
                 "eNum = StatsManager.getItemData[id] clamp+LogError if bag.num > recorded (0x1442AD0-0x1442BE8); "
                 "E_Alchemy(2)/unset -> dropped; entry gate: on failed battle only section types with bit in "
                 "0x80840000 (E_ShuangHanBattle=11, E_ActivityBattle=15) still emit lists"},
   {"method": "FightItemBag.GetPersistentItemsList", "rva": "0x1E51A54",
    "reads": "Item.ItemUseScence @ +0x20 (0x1E51BAC: cmp w8,#1)",
    "semantics": "E_Outside only; no source filter; no eNum; used as helper (no direct BL callers)"},
   {"method": "other ItemManager.GetItem callers", "status": "UNSCANNED for +0x20 loads",
    "note": "the two known consumers cover both checkout lists; exhaustive +0x20 xref left open (inlining)"}],
 "data": {
   "maze_items_examples": {"1101021": "E_MazeCurrency", "1237903": "E_MazeCurrency(EffData=[903])"},
   "outside_items_examples": {"1237901": "E_Currency(EffData=[901]) gold", "1240001": "E_Equip (兽主)",
                               "1209162": "随机兽主 display item"}}})

# ---------- 3. gift_consumers.json ----------
import subprocess
giftman_callers = ["AcceptTaskNode.InitRewardNode","AchievementUI.InitAchievement/RefreshOverView",
 "BagChoosePage.OnOpen","BattlePassAchievement.InitAchievement/RefreshOverView","BuffInfo.DropItemByBuff",
 "ExchangeItemNode.Refresh","CollegeCustomerDetil.Refresh x2","DailyGiftNode.RefreshItem",
 "GMMainPage.OnItemGetBtnClick","GameAPI.GetItemNumByGiftID","GameAPI.GetShowItemNumByGiftID x2",
 "GiftBoxDetail.CheckPreviewBtnShow/OnPreviewBtnClick","ItemComposePage.OnOpen",
 "GlobalFun.GetItemByGiftGroup","GlobalFun.GetItemNumByGiftGroup","MailModule.ReceiveAttachment",
 "MoonNpcEquip.Refresh x2","MoonPresigePage.DetailNode.RefreshNode","MoonTaskNode.InitRewardNode",
 "PowerItemUse.BTN_SelectItem","MissionManager.AddMissionMsg","QuestCollectItem.SetParam",
 "RespondersItemNode.InitRewardNode","RespondersModule.GetRewardList","RookieSignUI.InitView",
 "StarChartStoryRecall.ChapterItem.RefreshCommonItem"]
W("gift_consumers.json", {
 "class": "Example.Gift {GiftGroup, AwardType:GiftEAwardType, Probability[], GiftValue[], Num[], GiftShow[], ItemNum, EquibNum}",
 "enum GiftEAwardType": {"E_None":0,"E_material":1,"E_Random":2,"E_RandomInterval":3,"E_Pick":4,"E_BlindBox":5},
 "GiftManager.GetItem callers (33 BL sites, all display/preview/UI)": giftman_callers,
 "battle_or_checkout_consumers": "NONE — no FightModule/LogicBattle/StatsManager path calls GiftManager",
 "account_buff_gift_chain": [
   "GodSoonModule.GetAllSectionDropItemByAllBuff (0x13E34E4)",
   "-> BuffInfo.DropItemByBuff (0x14E4B4C): GiftManager.GetItem per gift id, copies contents (no RNG)",
   "-> callers: ChapterInfoView.ShowDropItem / AnniversaryTowerSectionView.ShowDropItem / BattlePassTab.ShowDropItem",
   "-> ALL UI PREVIEW (关卡详情的 buff 加成掉落预览)"],
 "native_random_resolver": {
   "GlobalFun.GetItemByGiftGroup(Random,group) 0x18D26FC": [
     "g = GiftManager.Instance.GetItem(group)",
     "if g.AwardType == E_material(1): return g.GiftValue            // fixed: whole list",
     "result = new List<int>()",
     "idx = GlobalFun.GetProbability(mRandom, g.Probability)          // single weighted pick",
     "result.Add(g.GiftValue[idx])",
     "return result"],
   "direct_BL_callers": 0,
   "interpretation": "resolver EXISTS natively (same GetProbability primitive as drops) but has no direct "
                     "native caller in 2.4 — likely invoked from the missing ILRuntime hotfix assembly or via "
                     "delegates; actual granting never depends on it because checkout rewards arrive pre-resolved"},
 "section_reward_fields": {
   "FirVReward(0x110)/VReward(0x120)/MopReward(0x128)":
     "no native settlement-path reader found; settlement rewards arrive as server-resolved RewardData "
     "(L2C_CheckoutMainMission.rewardData / L2C_SecSweep.rewardData); table fields feed UI preview chains",
   "confidence": "B (protocol-level settled; per-field offset xref blocked by GetItem inlining)"}})

# ---------- 4. gift_random_algorithm.json ----------
W("gift_random_algorithm.json", {
 "verdict": "CLIENT RESOLVER EXISTS; SERVER EXECUTES THE GRANT",
 "algorithm": {
   "fixed (E_material)": "GiftValue returned/used verbatim",
   "E_Random/E_RandomInterval/E_Pick/E_BlindBox (in GetItemByGiftGroup)":
     "single weighted pick: idx = GetProbability(rng, Probability); result = GiftValue[idx]",
   "GetProbability (0x18D2880)": "sum weights, Range(0,sum), subtract per entry — same primitive as drops",
   "multi_pick_or_interval": "GetItemNumByGiftGroup returns List<int[]> (item,num pairs); not fully disassembled this round",
   "num_field": "Gift.Num pairs with GiftValue; Num roll semantics for E_RandomInterval not confirmed"},
 "who_supplies_rng": "UNKNOWN for the orphaned resolver (no native caller); battle RNG is LogicBattle.mRandom for drops",
 "grant_path": {
   "checkout": "L2C_CheckoutMainMission.rewardData{rewardItem[itemId,itemNum,transform], rewardEquip[HeroEquip], transformHero[heroId,transform]}",
   "sweep": "L2C_SecSweep.rewardData — server resolves MopReward gifts and returns final items",
   "conclusion": "A-level: the client never rolls Gift for settlement; current Revival server granting from "
                 "Gift tables = reconstructing what the official server did, NOT executing client logic"}})

# ---------- 5. equipment_instance_writers.json ----------
W("equipment_instance_writers.json", {
 "HeroEquip (PlayerDbData)": {"Id":0x10,"TypeId":0x14,"Level":0x18,"Exp":0x1C,"Star":0x20,
   "Param":"EquipParam(0x28): At1..At6/Av1..Av6/Lock1..Lock6","LockState":0x30,"TimeSec":0x34,"SeasonId":0x38},
 "RewardData": {"rewardItem":"List<RewardItem{itemId,itemNum,transform}>","rewardEquip":"List<HeroEquip>",
                 "transformHero":"List<TransformHero{heroId,transform}>"},
 "instance_origin": {
   "client_creation": "NONE FOUND — no HeroEquip.ctor symbol/callers; instances arrive via protobuf deserialize",
   "server_assignment": "A/B-level: full instance (incl. Id, Star and random Param) arrives inside "
                        "L2C_CheckoutMainMission.rewardData.rewardEquip / L2C_SecSweep / mail; L2C_EquipUpdate(536) "
                        "pushes changes; L2C_EquipAll(555) full snapshot",
   "verdict": "HeroEquip.id = SERVER_ASSIGNED; star = SERVER_ASSIGNED from drop context "
              "(battle ADC picks star within Section band; outsideItems.quality is the star carrier, B); "
              "star is NOT derived from TypeId (1240|SS|P has no star dimension; GM tool sends "
              "equipId and star/attrbd as separate inputs) — see docs/knowledge/equipment/equipment_id_star_mapping.md",
   "initial_affix_rule": "A-level (2026-09-25): initial minor affix count = EquibStage[Star].MinorListMin "
                         "(1/2/3/3/4/4), cap = MinorListMax; consistent with EquibAttribBD.MinorAttrNum"},
 "battle_drop_ride_along": {
   "flow": "DropProp/兽主掉落 → FightItemBag.AddItem(source=FIGHT) → 1240xxx ItemUseScence=E_Outside → "
           "887.outsideItems{id=1240xxx,num,quality} → SERVER converts to HeroEquip instance",
   "quality_field": "bag ItemDataP.quality = FightItemData.Quality passthrough; for equib drops "
                    "quality is the STAR CARRIER (drop pipeline indexes EquibStage with it, B)",
   "eNum_field": "0 for outside items (only maze items carry StatsManager.getItemData counts)"},
 "static_roll_inputs": {
   "EquibBase": "EquibPart/EquibSuit/MainAttrType[]+MainAttrChance[]/MinorAttrType[]+MinorAttrChance[]",
   "EquibAttribBD": "quality+level → main attr values / minor attr counts and ranges",
   "EquibStage": "star-related preset attrs/feeding",
   "note": "these are the OFFICIAL parameter tables a server needs; the roll itself is server-side"}})

# ---------- 6. equipment_attribute_rng.json ----------
W("equipment_attribute_rng.json", {
 "verdict": "SERVER_GENERATED (client receives finished EquipParam)",
 "evidence": [
   "EquipParam{At1..At6,Av1..Av6,Lock1..Lock6} travels inside HeroEquip over the wire (RewardData/HeroEquipProto)",
   "no native attribute-roll routine writes EquipParam on the client; client EquipmentService-equivalents only "
   "display/merge (L2C_EquipUpdate handler merges by Id)",
   "strengthen-time bonus events (+3/6/9/12/15) are a SEPARATE path: client sends C2L_EquipStrengthen(115), "
   "server rolls and returns level+params — same server-side RNG domain"],
 "official_parameters_available": {
   "main_attr": "EquibBase.MainAttrType[] weighted by MainAttrChance[]",
   "minor_attr": "EquibBase.MinorAttrType[] weighted by MinorAttrChance[]; values from EquibAttribBD per quality+level",
   "locks": "EquipParam.Lock1..6 (unlock states, client-visible)"},
 "resolved_2026_09_25": "initial minor affix COUNT rule recovered (A): = EquibStage[Star].MinorListMin "
                        "(1/2/3/3/4/4), cap MinorListMax; two tables (EquibStage/EquibAttribBD.MinorAttrNum) agree",
 "unknown": "value roll distribution within EquibAttribBD ranges; whether 4/5/6★ initial count can "
            "hit MinorListMax (AttribBD rows 14000100/15000000/16000000/16151100 carry =Max); "
            "star distribution within the drop band"})

# ---------- 7/8. special rewards ----------
W("special_reward_consumers.json", {
 "ChallengeReward1(SectionTable.0x70)": {
   "verdict": "NOT A REWARD FIELD — it is a Language text key",
   "evidence": "values like 21101515 resolve in Language table to 挑战说明文案 "
               "('111%月钻掉落奖励\\n109%兽主掉落奖励\\n掉落1-3★兽主…'); pattern = relatedSectionID*10+variant",
   "impact": "correction to section_reward_coverage wording '127 个有 ChallengeReward1' — these are descriptions"},
 "ChestReward(0x11C)/ExpertChestReward(0x118)": {
   "verdict": "E_Chest ITEM ids (1203501/1203701 series; all values exist in Item with ItemType=E_Chest)",
   "model": "reward = chest ITEM granted into inventory; opening = item-use flow resolved server-side; "
            "ExpertChest additionally tracked by TaskCondition E_GetExpertChest(42) "
            "(TaskConditionLine same code 42)",
   "sections": {"ChestReward": 101, "ExpertChestReward": 101, "ChallengeReward1(text)": 127}},
 "trigger_models": {
   "CLAIM_BUTTON": ["PickTreasureBox(310) 活跃宝箱","QueryTowerReward(927)/ReceiveTowerReward(929)",
                     "Battlepass: QueryBattlePassInfo(935)/ReceiveBattlePass(941)/SignBattlePass(949)/"
                     "BuyBattlePassLevel(939)/BattlePassLevelReceiveReward(1059)",
                     "RaceSectionGetReward(1106)","GetCollectionAward(588)",
                     "FlipPickTreasureBox(1073) — E_PickChest pick-a-box UI"],
   "AUTO_ON_CLEAR (server-side resolve at checkout)": ["Section FirVReward/VReward → RewardData(152)",
                     "SecSweep → RewardData(1028)"],
   "ITEM_USE (open chest item)": ["ChestReward/ExpertChestReward chest items (ItemType E_Chest=18)"],
   "TASK_EVENT": ["E_GetExpertChest(42) reported into task/condition system"],
   "QUERY_PLUS_CLAIM (worldboss)": ["QueryWorldBossInfo(415)/WorldBossSearch(407)/WorldBossOpenSearchChest(409)/"
                                     "WorldBossAct(417)/WorldBossLetter(419)/WorldBossQuestSelect(471) — all SendBattle"],
   "NO_SEND_POINT (never sent by 2.4)": ["C2L_CheckoutMainMission(150)","C2L_PrepareMainMission(151)",
                     "C2L_FightDropInfo(323)","NoviceFinish(217)","C2L_FightKillInfo? NO — 316 has send",
                     "correction: MatchEnter(1082)/BattleEnter(1085) DO have send points (earlier list wrong)"]}
})

W("special_reward_protocols.json", {
 "note": "send-channel facts from analysis/protocol/protocol_catalog.json (fixed build)",
 "reward_related_c2l_with_send": {
   "PickTreasureBox": 310, "FlipPickTreasureBox": 1073, "GetCollectionAward": 588,
   "QueryTowerReward": 927, "ReceiveTowerReward": 929,
   "QueryBattlePassInfo": 935, "ReceiveBattlePass": 941, "SignBattlePass": 949,
   "BuyBattlePassLevel": 939, "BattlePassLevelReceiveReward": 1059,
   "RaceSectionGetReward": 1106, "SecSweep": 1027,
   "WorldBossSearch": 407, "WorldBossOpenSearchChest": 409, "QueryWorldBossInfo": 415,
   "WorldBossAct": 417, "WorldBossLetter": 419, "WorldBossQuestSelect": 471,
   "QueryWorldBossOpenTime": 679, "WorldBossSelectHero": 701,
   "ActivityMissionData": 858, "QueryActivityMissionRecord": 618, "ActivityMissionRecordSave": 620},
 "delivery": {
   "settlement_rewards": "L2C_CheckoutMainMission(152).rewardData / L2C_SecSweep(1028).rewardData",
   "new_equips": "inside RewardData.rewardEquip; subsequent changes via L2C_EquipUpdate(536); full list L2C_EquipAll(555)",
   "item_changes": "L2C_ItemUpdate(553)",
   "task_progress": "L2C_TaskUpdate(558)"}})

print("wrote 8 json files to", OUT)
