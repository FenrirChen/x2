"""ReportCurrency conversion and DropValues budget tier policy.

REVIVAL_COMPATIBILITY / USER_DECISION 2026-09-26:
  - E_ReportCurrency (FunctionEff=14) battle proxies convert to the account currency
    (EffData=[bucket, perUnit]; bucket -> E_Currency Item, table-derived) and never
    enter rewardItem/inventory as the faceless proxy item.
  - DropValues budgets: LOW=1000 / MID=3000 / HIGH=5000 by official DifficultyLevel
    (1-3 / 4-6 / 7+); sections without a difficulty default to MID.
"""
import asyncio
import json

from tests.unit.test_battle import packet, request
from tests.unit.test_economy import env, rewards  # noqa: F401 (fixtures)
from x2server.messages.battle import CHECKOUT, OUTSIDE_ITEM, PROFILE_HERO
from x2server.player.battle import BattleService
from x2server.player.drop_budget import DropBudgetCompatibilityPolicy
from x2server.player.economy import EconomyService
from x2server.player.reward_system import ReportCurrencyResolver, RuntimeDropResolver
import pytest


def test_report_currency_resolver_maps_all_known_proxies():
    resolver = ReportCurrencyResolver(_load_map())
    assert len(resolver.mapping) == 68  # every official E_ReportCurrency proxy
    assert resolver.unresolvable == set()  # all buckets have an account E_Currency
    assert resolver.lookup(1101076) == (1237901, 28)   # bucket 901 -> gold
    assert resolver.lookup(1101060) == (1237912, 10)   # bucket 912 -> 月钻 (1237912)
    assert resolver.lookup(9999999) is None


def test_all_report_currency_proxies_use_runtime_battle_dispatch(env):
    _, economy, _ = env
    mapping = _load_map()["items"]
    profile = {"section_id": 2133101, "runtime_allowlist_mode": "DYNAMIC_ALLOWED"}
    run = {"uuid": "all-report-currency", "section_id": 2133101, "settled": 0}
    for proxy_text, row in mapping.items():
        proxy_id = int(proxy_text)
        grants, pending, blocked, equipment = economy.runtime_drops.resolve(
            run=run, profile=profile,
            outside_items=[OUTSIDE_ITEM.encode({"id": proxy_id, "num": 2,
                                                "quality": 1, "eNum": 0})], success=True)
        assert [(g.source, g.item_id, g.quantity) for g in grants] == [
            ("REPORT_CURRENCY", row["account_item_id"], 2 * row["per_unit"])]
        assert pending == blocked == equipment == []


def _load_map():
    import json
    from importlib.resources import files
    return json.loads(files("x2server").joinpath("data/report_currency_map.json").read_text(encoding="utf-8"))


def test_unknown_bucket_proxy_is_parked_not_guessed(env):
    """A proxy whose bucket has no account currency is parked (never guessed)."""
    store, economy, ctx = env
    economy.report_currency = ReportCurrencyResolver({"items": {}, "unresolvable": [1101076]})
    service = BattleService(store, economy)
    economy.runtime_drops.report_currency = economy.report_currency
    run = enter_gold(service, ctx)
    result = checkout(service, ctx, outside=({"id": 1101076, "num": 5, "quality": 1, "eNum": 0},))
    assert result.values["result"] == 10
    pending = store.db.execute("SELECT item_id, quantity FROM pending_reward_instances "
                               "WHERE run_id=?", (run,)).fetchall()
    assert [tuple(r) for r in pending] == [(1101076, 5)]
    assert 1101076 not in rewards(result.values["rewardData"])


def enter_gold(service, ctx):
    values = request()
    values.update(missionId=2130101, chapter=2030100, sceneId=2230101)
    result = asyncio.run(service.enter(ctx, packet(values)))
    assert result.values["result"] == 10
    return result.values["uuid"]


def checkout(service, ctx, outside, request_id=1):
    raw = CHECKOUT.encode({"chapterId": 2030100, "sectionId": 2130101,
        "success": True, "fightTime": 120,
        "outsideItems": [OUTSIDE_ITEM.encode(row) for row in outside]})
    return asyncio.run(service.checkout(ctx, packet({"checkout": raw},
        name="C2L_CheckoutMainMissionSign", request_id=request_id)))


def test_proxy_conversion_merges_and_skips_inventory(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    enter_gold(service, ctx)
    result = checkout(service, ctx, outside=(
        {"id": 1101076, "num": 4, "quality": 1, "eNum": 0},   # 4 x 28 = 112
        {"id": 1101076, "num": 1, "quality": 1, "eNum": 0},   # +28 -> merged 140
        {"id": 1101077, "num": 2, "quality": 1, "eNum": 0}))  # 2 x 84 = 168 -> merged 308
    assert result.values["result"] == 10
    delivered = rewards(result.values["rewardData"])
    assert delivered[1237901] == 308  # single merged account-currency grant
    assert 1101076 not in delivered and 1101077 not in delivered
    assert store.db.execute("SELECT COUNT(*) FROM inventory WHERE item_id IN (1101076,1101077)"
                            ).fetchone()[0] == 0
    assert store.get(1)["snapshot"]["gold"] == 308


def test_duplicate_checkout_does_not_reconvert(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    enter_gold(service, ctx)
    first = checkout(service, ctx, outside=({"id": 1101076, "num": 4, "quality": 1, "eNum": 0},))
    gold = store.get(1)["snapshot"]["gold"]
    replay = checkout(service, ctx, outside=({"id": 1101076, "num": 4, "quality": 1, "eNum": 0},),
                      request_id=2)
    assert replay.values == first.values
    assert store.get(1)["snapshot"]["gold"] == gold


def test_fixed_rewards_and_sweep_unaffected(env):
    """First-clear crystal and normal VReward keep flowing alongside conversions."""
    store, economy, ctx = env
    service = BattleService(store, economy)
    enter_gold(service, ctx)
    result = checkout(service, ctx, outside=({"id": 1101076, "num": 1, "quality": 1, "eNum": 0},))
    delivered = rewards(result.values["rewardData"])
    assert delivered[1237901] == 28
    assert delivered.get(1237902) == 30  # first-clear fixed reward intact
    # sweep path (MopReward) is exercised by the existing sweep tests.


def test_beast_dungeon_moon_diamond_proxy_checkout_and_replay(env):
    store, economy, ctx = env
    service = BattleService(store, economy)
    with store.db:
        store.db.execute("INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)",
            (1, service.catalog.sections[2133101]["OpenParam"], "prerequisite"))
    values = request()
    values.update(missionId=2133101, chapter=2033100, sceneId=2233101)
    entered = asyncio.run(service.enter(ctx, packet(values)))
    assert entered.values["result"] == 10
    run = entered.values["uuid"]
    raw = CHECKOUT.encode({"chapterId": 2033100, "sectionId": 2133101,
        "success": True, "fightTime": 120,
        "outsideItems": [OUTSIDE_ITEM.encode({"id": 1101060, "num": 90,
                                               "quality": 4, "eNum": 0})]})
    def submit(request_id):
        return asyncio.run(service.checkout(ctx, packet({"checkout": raw},
            name="C2L_CheckoutMainMissionSign", request_id=request_id)))
    first = submit(1)
    assert first.values["result"] == 10
    assert rewards(first.values["rewardData"])[1237912] == 90 * _load_map()["items"]["1101060"]["per_unit"]
    assert 1101060 not in rewards(first.values["rewardData"])
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237912").fetchone()[0] == 900
    assert store.db.execute("SELECT COUNT(*) FROM inventory WHERE item_id=1101060").fetchone()[0] == 0
    assert store.db.execute("SELECT COUNT(*) FROM pending_reward_instances WHERE run_id=?", (run,)).fetchone()[0] == 0
    audit = store.db.execute("SELECT sources,blocked FROM reward_settlement_audit WHERE run_id=?", (run,)).fetchone()
    assert json.loads(audit[1]) == []
    assert json.loads(audit[0])["REPORT_CURRENCY"][0]["item_id"] == 1237912
    replay = submit(2)
    assert replay.values == first.values
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237912").fetchone()[0] == 900


@pytest.mark.parametrize("bucket", (901, 904, 906, 907, 912, 913, 925, 981))
def test_report_currency_families_settle_as_account_items(env, bucket):
    store, economy, ctx = env
    proxy_id, mapping = next((int(i), row) for i, row in _load_map()["items"].items()
                             if row["bucket"] == bucket)
    service = BattleService(store, economy)
    enter_gold(service, ctx)
    result = checkout(service, ctx, outside=({"id": proxy_id, "num": 2,
                                              "quality": 1, "eNum": 0},))
    assert result.values["result"] == 10
    delivered = rewards(result.values["rewardData"])
    assert delivered[mapping["account_item_id"]] >= 2 * mapping["per_unit"]
    assert proxy_id not in delivered
    assert store.db.execute("SELECT COUNT(*) FROM inventory WHERE item_id=?", (proxy_id,)).fetchone()[0] == 0


def test_budget_tiers_by_official_difficulty():
    sections = {2130101: 1, 2130105: 5, 2130201: 2, 2133101: 1, 2133110: 10,
                2110801: 0, 2190001: 0}
    policy = DropBudgetCompatibilityPolicy(sections)
    assert policy.tier_for(2130101) == ("LOW", True)    # Difficulty1
    assert policy.tier_for(2130105) == ("MID", True)    # Difficulty5 (thirds: 4-6 MID)
    assert policy.tier_for(2133101) == ("LOW", True)    # Difficulty1 (moon phase)
    assert policy.tier_for(2133110) == ("HIGH", True)   # Difficulty10 (7+ HIGH)
    assert policy.tier_for(2110801) == ("MID", False)   # no difficulty -> default MID
    assert policy.budget_for(2130101) == [1000] * 27
    assert policy.budget_for(2130203) == [3000] * 27    # Difficulty4? -> see tier map
    assert policy.budget_for(2133110) == [5000] * 27


def test_resolver_tier_boundaries():
    policy = DropBudgetCompatibilityPolicy({100: 3, 101: 4, 102: 6, 103: 7, 104: 0})
    assert policy.tier_for(100) == ("LOW", True)   # 1-3
    assert policy.tier_for(101) == ("MID", True)   # 4-6
    assert policy.tier_for(102) == ("MID", True)
    assert policy.tier_for(103) == ("HIGH", True)  # 7+
    assert policy.tier_for(104) == ("MID", False)  # unknown -> MID + telemetry


def test_budget_carriers_follow_policy(env):
    """Both budget carriers (130 entry dropData + 266 answer) follow the policy for
    the section. 2110801 has no official DifficultyLevel -> default MID (3000);
    tier mapping by DifficultyLevel is covered by test_budget_tiers_* above."""
    store, economy, ctx = env
    battle = BattleService(store, economy)
    values = request()  # missionId 2110801, chapter 2010100, scene 2210801
    entered = asyncio.run(battle.enter(ctx, packet(values)))
    assert entered.values["result"] == 10
    from x2server.messages.battle import FIGHT_DATA, DROP_DATA
    expected = battle.drop_budget.budget_for(2110801)
    assert expected == [3000] * 27  # default MID: no 1,000,000 anywhere anymore
    entry_data = FIGHT_DATA.decode(entered.values["data"])
    assert list(DROP_DATA.decode(entry_data["dropData"])["dropValues"]) == expected
    drops = asyncio.run(battle.drop_data(ctx, packet(
        {"missionId": 2110801, "chapterId": 2010100}, name="C2L_FightDropData")))
    assert list(DROP_DATA.decode(drops.values["data"])["dropValues"]) == expected


def _load_entry_catalog():
    import json
    return json.load(open("src/x2server/data/battle_entry_catalog.json", encoding="utf-8"))
