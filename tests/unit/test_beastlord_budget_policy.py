"""Approved value caps cover every section while isolating the beastlord group."""
import json
from importlib.resources import files

from x2server.player.battle_entry import BattleEntryCatalog
from x2server.player.drop_budget import DropBudgetCompatibilityPolicy


def rules():
    return json.loads(files('x2server').joinpath('data/beastlord_budget_rules.json').read_text(encoding='utf8'))


def test_all_sections_preserve_other_groups_and_exceptions():
    sections = BattleEntryCatalog().sections
    policy = DropBudgetCompatibilityPolicy({k: r.get('DifficultyLevel', 0) for k, r in sections.items()})
    config = rules()
    changed = 0
    for sid, row in sections.items():
        difficulty = row.get('DifficultyLevel', 0)
        old = 1000 if 1 <= difficulty <= 3 else 5000 if difficulty >= 7 else 3000
        values = policy.budget_for(sid)
        assert len(values) == 29
        assert values[27] == 3000
        assert values[28] == 3000
        assert all(value == old for group, value in enumerate(values) if group not in (5, 27, 28))
        if row['Type'] == 20:
            assert values == [old] * 27 + [3000, 3000]
            assert str(sid) not in config['sections']
        elif str(sid) not in config['sections']:
            assert values == [old] * 27 + [3000, 3000]
        else:
            entry = config['sections'][str(sid)]
            assert values[5] == 30 * entry['percent']
            assert entry['difficulty'] == difficulty and entry['section_type'] == row['Type']
        changed += values[5] != old
    assert len(sections) == 3203
    assert len(config['sections']) == changed == 210
    assert config['coverage']['official_rate'] == 100
    assert config['coverage']['compatibility_curve'] == 110
    assert config['coverage']['battlepass_unchanged'] == 1800


def test_official_chapter_variations_and_unknown_sections():
    sections = BattleEntryCatalog().sections
    policy = DropBudgetCompatibilityPolicy({k: r.get('DifficultyLevel', 0) for k, r in sections.items()})
    # These rates are independently read from official descriptions, not derived
    # from difficulty. Both Hui moons are level 9, with distinct chapter rewards.
    assert policy.budget_for(2133101)[5] == 3000   # 100%
    assert policy.budget_for(2133107)[5] == 4740   # 158%
    assert policy.budget_for(2133109)[5] == 6000   # 200%
    assert policy.budget_for(2133209)[5] == 6420   # 214%
    assert policy.budget_for(2133110)[5] == 13200  # 440%
    assert policy.budget_for(-1) == [3000] * 29
    assert -1 in policy.unknown_hits
    assert DropBudgetCompatibilityPolicy({}).budget_for(2133110) == [3000] * 29


def test_compatibility_curve_is_only_used_for_exported_eligible_sections():
    config = rules()
    curve = [100, 106, 113, 121, 131, 143, 158, 177, 200, 440]
    for entry in config['sections'].values():
        if entry['source'] == 'compatibility_curve':
            assert entry['section_type'] in (2, 18)
            assert entry['percent'] == curve[entry['difficulty'] - 1]
    # Having level 10 alone does not create an equipment drop profile.
    policy = DropBudgetCompatibilityPolicy({999999: 10})
    assert policy.budget_for(999999) == [5000] * 27 + [3000, 3000]
