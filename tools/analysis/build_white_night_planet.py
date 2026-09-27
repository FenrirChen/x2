"""Rebuild evidence indexes for the client College (白夜行星) system.

Reads decoded client tables and the already recovered protocol catalogue. It does
not open the active save or modify server code.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = ROOT.parent / "analysis/drop_archaeology/full_tables"
OUT = ROOT / "analysis/white_night_planet"


def rows(name):
    return json.loads((UPSTREAM / f"{name}.json").read_text(encoding="utf-8"))["records"]


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# UI action, C2L basename, sending method, response handler, implied state.
# These method names are from the official 2.4 dump.cs and script.json.
FLOWS = [
    ("基地入口查询", "QueryGrowthBase", "CollegeModule$$SendQueryGrowthBase", "CollegeModule$$OnGetQueryGrowthBaseData", "基地快照/计时器读取"),
    ("遗迹解锁查询", "UnlockExploreRuin", "CollegeModule$$SendUnlockExploreRuin", "CollegeModule$$OnReceiveUnlockExploreRuin", "遗迹开放状态读取"),
    ("建筑升级", "BuildingUpgrade", "CollegeUpgradeModule$$UpgradeClick", "CollegeUpgradeModule$$OnReceiveBuildUpgrade", "建筑等级/建造队列/资源"),
    ("建筑加速", "BuildSpeedUP", "CollegeUpgradeModule.<>c__DisplayClass49_0$$<C2L_BuildSpeedUP>b__0", "CollegeUpgradeModule$$OnHandleSpeedupResult", "队列结束时间/加速道具"),
    ("建筑升星", "BuildStarUP", "CollegeUpgradeModule$$UpgradeClick", "CollegeUpgradeModule$$OnReceiveBuildStarUPMsg", "建筑星级/资源"),
    ("建筑完成", "BuildCrystalFinish", "CollegeUpgradeModule.<>c__DisplayClass32_0$$<CompleteClick>b__0", "CollegeUpgradeModule$$OnReceiveBuildCrystalFinishMsg", "建造状态/奖励"),
    ("星能兑换体力", "ExchangePower", "CollegeModule$$SendExchangePower", "CollegeModule$$OnReceiveExchangePowerMsg", "星能/额外体力"),
    ("派遣开始", "StartExplore", "CollegeModule$$SendStartExplore", "CollegeModule$$OnReceiveStartExploreMsg", "派遣槽/英雄占用/结束时间/消耗"),
    ("派遣完成", "FinishExplore", "CollegeModule$$SendFinishExplore", "CollegeModule$$OnReceiveFinishExploreMsg", "派遣槽/奖励/遗迹经验"),
    ("派遣取消", "CancelExplore", "CollegeModule$$SendCancelExplore", "CollegeModule$$OnReceiveCancelExploreMsg", "派遣槽/退还星能"),
    ("派遣加速", "ExploreSpeed", "CollegeModule$$SendExploreSpeed", "CollegeModule$$OnReceiveExploreSpeed", "派遣结束时间/资源"),
    ("训练开始", "StartTrain", "CollegeModule$$SendStartTrain", "CollegeModule$$OnReceiveStartTrain", "训练槽/英雄占用/结束时间/消耗"),
    ("训练完成", "FinishTrain", "CollegeModule$$SendFinishTrain", "CollegeModule$$OnReceiveFinishTrainMsg", "训练槽/英雄经验/等级"),
    ("训练取消", "CancelTrain", "CollegeModule$$SendCancelTrain", "CollegeModule$$OnReceiveCancelTrainMsg", "训练槽/退还星能"),
    ("祈祷开始", "BuildStartPrayGod", "CollegeWonderModule$$NetStartPray", "CollegeWonderModule$$OnReceiveBuildStartPrayGodMsg", "祈祷队列/英雄/材料/计时"),
    ("祈祷停止", "BuildCancelPrayGod", "CollegeWonderModule$$NetStopPray", "CollegeWonderModule$$OnReceiveBuildCancelPrayGodMsg", "祈祷队列/材料"),
    ("祈祷领奖", "BuildRewardPrayGod", "CollegeWonderModule$$NetGetAward", "CollegeWonderModule$$OnReceiveBuildRewardPrayGodMsg", "祈祷队列/奖励账本"),
    ("祈祷加速", "BuildQuickenPrayGod", "CollegeWonderModule$$NetSpeedUp", "CollegeWonderModule$$OnReceiveBuildQuickenPrayGodMsg", "祈祷结束时间/道具"),
    ("炼金主页", "AlchemyMainData", "CollegeAlchemyModule$$SendAlchemyMainData", "CollegeAlchemyModule$$OnReceiveAlchemyMainDataMsg", "炼金快照读取"),
    ("炼金顾客", "SingleCustomerInfo", "CollegeAlchemyModule$$SendSingleCustomerInfo", "CollegeAlchemyModule$$OnReceiveSingleCustomerInfoMsg", "顾客槽读取"),
    ("炼金生产", "MakeItem", "CollegeAlchemyModule$$SendMakeItem", "CollegeAlchemyModule$$OnReceiveMakeItemMsg", "生产槽/材料/计时"),
    ("炼金生产加速", "MakIngSpeed", "CollegeAlchemyModule$$SendMakIngSpeed", "CollegeAlchemyModule$$OnReceiveMakIngSpeedMsg", "生产结束时间/资源"),
    ("炼金交易完成", "AlchemyFinish", "CollegeAlchemyModule$$SendAlchemyFinish", "CollegeAlchemyModule$$OnReceiveAlchemyFinishMsg", "顾客订单/售价/奖励"),
    ("炼金顾客对话", "AlchemyButtonClick", "CollegeAlchemyModule$$SendAlchemyButtonClick", "CollegeAlchemyModule$$OnReceiveAlchemyButtonClickMsg", "顾客交互状态"),
    ("炼金收取", "AlchemyCollect", "CollegeAlchemyModule$$SendAlchemyCollect", "CollegeAlchemyModule$$OnReceiveAlchemyCollectMsg", "生产槽/物品/配方经验"),
    ("炼金购买", "AlchemyBuy", "CollegeAlchemyModule$$SendAlchemyBuy", "CollegeAlchemyModule$$OnReceiveAlchemyBuyMsg", "生产位/资源"),
    ("炼金取消", "AlchemyMakeCancel", "CollegeAlchemyModule$$SendMakeCancle", "CollegeAlchemyModule$$OnReceiveMakeCancle", "生产槽/返还"),
    ("炼金一键收取", "AlchemyOnekeyCollect", "CollegeAlchemyModule$$SendAlchemyOnekeyCollect", "CollegeAlchemyModule$$OnReceiveOnceGet", "多生产槽/奖励账本"),
    ("装备洗炼随机", "WashingRoomRandomAttri", "CollegeModule$$SendWashingRoomRandomAttri", "CollegeModule$$OnRecieveWashingRoomRandomAttri", "装备随机属性/日次数"),
    ("装备洗炼操作", "WashingRoomOpt", "CollegeModule$$SendWashingRoomOpt", "CollegeModule$$OnRecieveWashingRoomOpt", "装备属性/材料/日次数"),
    ("公会建筑协助", "HelpPowerSpeed", "CollegeModule$$SendHelpBuidInfo", "CollegeModule$$OnGetHelpPowerSpeed", "协助速度/奖励"),
    ("协助资格查询", "HelpPowerSpeedValid", "CollegeModule$$SendHelpPowerSpeedVaild", "CollegeModule$$OnGetHelpPowerSpeedVaild", "协助次数/资格读取"),
]


def build_protocol():
    catalog = json.loads((ROOT / "analysis/protocol/protocol_catalog.json").read_text(encoding="utf-8"))["catalog"]
    lookup = {(r["direction"], r["message_name"]): r for r in catalog}
    methods = {r["Name"]: r["Address"] for r in json.loads(
        (ROOT.parent / "tools/Il2CppDumper-bin/script.json").read_text(encoding="utf-8"))["ScriptMethod"]}
    matrix, gaps = [], []
    for action, name, sender, handler, mutation in FLOWS:
        request, response = lookup[("C2L", name)], lookup[("L2C", name)]
        if request["client_status"] != "SEND_SITES_FOUND":
            raise ValueError(f"{name} no longer has a client Send site")
        # The two club-help requests are indirect, with cached request objects.
        status = "INDIRECT" if name in ("HelpPowerSpeed", "HelpPowerSpeedValid") else "REAL_SEND"
        send_rva = methods.get(sender)
        handler_rva = methods.get(handler)
        matrix.append({"Action": action, "C2L": "C2L_" + name,
            "C2L ID": request["message_id"], "Send point": sender +
            (f" @ {send_rva:#x}" if send_rva is not None else " @ RVA unresolved"),
            "Request fields": ",".join(request["protobuf_fields"]),
            "L2C": "L2C_" + name, "L2C ID": response["message_id"],
            "Handler": handler + (f" @ {handler_rva:#x}" if handler_rva is not None else " @ RVA unresolved"),
            "Response fields used": ",".join(response["protobuf_fields"]) + " [declared; exact reads pending native field audit]",
            "Server mutation implied": mutation, "Status": status})
        coverage = "PARTIAL" if name == "QueryGrowthBase" else "STUB" if name == "UnlockExploreRuin" else "MISSING"
        gaps.append({"C2L": "C2L_" + name, "C2L ID": request["message_id"],
            "Current Server": coverage, "Reason": (
                "Returns fixed level-one buildings; no persisted College state" if coverage == "PARTIAL" else
                "Returns code 13 without ruin records" if coverage == "STUB" else
                "No College handler / state transaction"),
            "Required dependency": mutation})
    for filename, records in (("protocol_matrix.csv", matrix), ("server_gap_matrix.csv", gaps)):
        with (OUT / filename).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)
    return matrix


def build_static():
    names = {
        "collegebuilding": ("ID", "building definition / unlock / level and star references", ["collegelevel", "collegestarlevel", "language"]),
        "collegelevel": ("BuildID", "building level gates and effects", ["collegebuilding", "item"]),
        "collegestarlevel": ("BuildID", "building star gates and effects", ["collegebuilding", "item"]),
        "collegewonderskill": ("AddID", "civilization wonder modifiers", ["collegebuilding", "language"]),
        "collegeexplore": ("ID", "timed dispatch locations, costs, reward groups", ["gift", "item", "language"]),
        "collegerecipe": ("RecipeID", "alchemy production inputs, outputs and timer", ["item", "language"]),
        "collegequest": ("QuestID", "alchemy customer quests and reward groups", ["collegecustomer", "gift", "item"]),
        "collegecustomer": ("CustomerID", "alchemy customer dialogue / preferences", ["language", "collegerecipe"]),
        "collegeequibreset": ("ID", "washing room material cost options", ["item"]),
        "functionopen": ("ID", "account-level base and wonder entry gates", ["language"]),
        "gift": ("GiftGroup", "referenced dispatch and quest rewards", ["item"]),
        "item": ("ItemID", "referenced resources / output items", ["language"]),
        "sectiontable": ("SectionID", "negative check: no CollegeExplore ID is a battle SectionID", []),
        "activity": ("ActivityID", "negative check: Activity 28001 is a separate timed activity", []),
    }
    data = {name: rows(name) for name in names}
    building = data["collegebuilding"]
    level_ids = {i for row in building for i in row.get("LevelID", [])}
    star_ids = {i for row in building for i in row.get("StarID", [])}
    groups = {row["Reward"] for row in data["collegeexplore"]}
    groups.update(g for row in data["collegequest"] if row.get("AwardType", {}).get("value") == 1
                  for g in row.get("AwardGroup", []))
    item_ids = {row["ProduceID"] for row in data["collegeexplore"]}
    item_ids.update(row["ProductID"] for row in data["collegerecipe"])
    item_ids.update(i for row in data["collegerecipe"] for i in row.get("ItemGroup", []))
    item_ids.update(i for row in data["collegeequibreset"] for key in ("EquibReastItem1", "EquibReastItem2") for i in row.get(key, []))
    item_ids.update(i for row in data["gift"] if row["GiftGroup"] in groups for i in row.get("GiftValue", []))
    selected = {
        "collegebuilding": {row["ID"] for row in building}, "collegelevel": level_ids,
        "collegestarlevel": star_ids, "collegewonderskill": {row["AddID"] for row in data["collegewonderskill"]},
        "collegeexplore": {row["ID"] for row in data["collegeexplore"]},
        "collegerecipe": {row["RecipeID"] for row in data["collegerecipe"]},
        "collegequest": {row["QuestID"] for row in data["collegequest"]},
        "collegecustomer": {row["CustomerID"] for row in data["collegecustomer"]},
        "collegeequibreset": {row["ID"] for row in data["collegeequibreset"]},
        "functionopen": {21902, 21912}, "gift": groups, "item": item_ids,
        "sectiontable": set(), "activity": set(),
    }
    result = {"source": str(UPSTREAM), "evidence_level": "A static client table",
        "tables": []}
    for name, (pk, meaning, refs) in names.items():
        ids = selected[name]
        available = {row[pk] for row in data[name]}
        if not ids <= available:
            raise ValueError(f"{name} has unresolved references: {sorted(ids - available)}")
        result["tables"].append({"table": name, "row_count": len(data[name]),
            "primary_key": pk, "related_row_ids": sorted(ids),
            "related_count": len(ids), "field_semantics": meaning,
            "references": refs})
    dump(OUT / "static_catalog.json", result)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    matrix = build_protocol()
    static = build_static()
    print(f"{len(matrix)} request flows, {len(static['tables'])} static tables")


if __name__ == "__main__":
    main()
