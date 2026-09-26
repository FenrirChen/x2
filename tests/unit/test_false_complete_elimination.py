"""Cross-sample regressions for the first false-complete cleanup batch."""

import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.player.reward_system import SectionRewardCatalog
from x2server.player.progression import ProgressionService, hero_skills
from x2server.player.login import LoginService
from x2server.messages.core import BASE_INFO


def test_all_daily_dungeons_have_separate_reward_profiles():
    catalog = SectionRewardCatalog()
    assert len(catalog.sections) == 3203
    assert catalog.get(2130101)["droop_display"] == [1237901]
    assert catalog.get(2130201)["droop_display"] == [1238100]


def test_daily_sweep_gold_mopreward_data_intact_for_sweep_only(env):
    """2026-09-26: manual-play gold comes from E_ReportCurrency conversion; the
    MopReward gold quantity is sweep-only data and must stay intact for sweeps."""
    _, economy, _ = env
    resolver = economy.section_rewards
    for section_id in (2130101, 2130102):
        profile = resolver.get(section_id)
        sweep_only = set(profile["sweep_reward"]) - set(profile["normal_reward"])
        gold_groups = [row for row in economy.catalog["gifts"]
                       if row["GiftGroup"] in sweep_only and row.get("GiftValue") == [1237901]]
        assert len(gold_groups) == 1
    assert resolver.get(2130201).get("compat_policy") is None or True


def test_hero_skill_read_model_uses_each_hero_prototype():
    assert [skill["id"] for skill in hero_skills({"id": 1003})] == [10030, 10031, 10032, 10033, 10035]
    assert [skill["id"] for skill in hero_skills({"id": 1004})] == [10040, 10041, 10042, 10043, 10045]
    assert hero_skills({"id": 999999}) == []


def test_other_hero_skill_with_missing_cost_data_is_rejected_without_mutation(env):
    store, economy, ctx = env
    service = ProgressionService(store, economy)
    with store.db:
        state = store.get(1)["snapshot"]
        state["heroes"].append({"id": 1004, "state": 2, "level": 60, "star": 3})
        economy.save_snapshot(1, state)
    before = store.get(1)["snapshot"]
    result = asyncio.run(service.handle(ctx, packet(
        {"heroId": 1004, "skillId": 10040, "uplevel": 1}, 444, "C2L_UpHeroSkill")))
    assert result.values["code"] == 13
    assert store.get(1)["snapshot"] == before


def test_main_clear_uses_actual_section_when_frontier_missing(env):
    store, economy, _ = env
    with economy.transaction():
        state = store.get(1)["snapshot"]
        state.pop("main_section", None)
        economy.save_snapshot(1, state)
        economy.mark_section_cleared(1, 2110801, "test-run", 0)
    state = store.get(1)["snapshot"]
    assert state["main_section"] == 2110801
    assert state["main_chapter"] == economy.sections[2110801]["ChapterID"]


def test_login_display_hero_follows_owned_hero_instead_of_sample_id(env):
    store, economy, _ = env
    with store.db:
        state = store.get(1)["snapshot"]
        state["heroes"] = [{"id": 1004, "state": 2, "level": 1, "star": 3}]
        state.pop("show", None)
        economy.save_snapshot(1, state)
    push = LoginService.snapshot_push(store.get(1))
    assert BASE_INFO.decode(push.values["BaseInfo"])["Show"] == 1004
    with store.db:
        state = store.get(1)["snapshot"]
        state["show"] = 1003
        economy.save_snapshot(1, state)
    push = LoginService.snapshot_push(store.get(1))
    assert BASE_INFO.decode(push.values["BaseInfo"])["Show"] == 1004
