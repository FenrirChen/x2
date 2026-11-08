import importlib.util
import sys
from pathlib import Path

import pytest


TOOL = Path(__file__).resolve().parents[2] / "tools" / "patch_daily_dungeon.py"
SPEC = importlib.util.spec_from_file_location("patch_daily_dungeon", TOOL)
assert SPEC is not None and SPEC.loader is not None
sys.path.insert(0, str(TOOL.parent))
patch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch)


def table(rows):
    """DailyDungeon plaintext: 4-byte count, then outer key + row per entry."""
    out = bytearray(len(rows).to_bytes(4, "little"))
    for key, open_time in rows:
        record = patch.varint(1 << 3) + patch.varint(key)
        for value in open_time:
            record += patch.varint(8 << 3) + patch.varint(value)
        out += patch.varint(1 << 3) + patch.varint(key)
        out += patch.varint(2 << 3 | 2) + patch.varint(len(record)) + record
    return bytes(out)


def open_times(plain):
    rows = {}
    for outer in patch.parse_message(plain, 4)[0]:
        if outer.field != 2:
            continue
        inner = patch.parse_message(outer.value)[0]
        key = next(v.value for v in inner if v.field == 1)
        rows[key] = [v.value for v in inner if v.field == 8]
    return rows


def test_opens_only_the_four_gated_daily_dungeons():
    rows = [(2030500, [1, 1, 0, 1, 0, 1, 0]),
            (2030600, [1, 0, 1, 0, 1, 0, 1]),
            (2030700, [1, 1, 0, 1, 0, 1, 0]),
            (2031200, [1, 0, 1, 0, 1, 0, 1]),
            (2030800, [1, 1, 1, 1, 0, 1, 1]),
            (2031300, [1, 1, 1, 1, 1, 1, 1])]
    plain = table(rows)
    repaired, hits = patch.patch_plaintext(plain)
    assert len(repaired) == len(plain)
    assert sorted({key for key, _ in hits}) == sorted(patch.TARGET_KEYS)
    assert len(hits) == 12
    changed = [i for i, (a, b) in enumerate(zip(plain, repaired)) if a != b]
    assert changed == sorted(offset for _, offset in hits)
    assert all(plain[i] == 0 and repaired[i] == 1 for i in changed)

    after = open_times(repaired)
    for key in patch.TARGET_KEYS:
        assert after[key] == [1] * 7
    assert after[2031300] == [1] * 7
    # A closed weekday on a row outside the four targets must survive untouched.
    assert after[2030800] == [1, 1, 1, 1, 0, 1, 1]


def test_leaves_an_already_open_table_alone():
    plain = table([(2030500, [1] * 7), (2030800, [1] * 7)])
    repaired, hits = patch.patch_plaintext(plain)
    assert repaired == plain
    assert hits == []


def test_splice_keeps_length_and_refuses_an_ambiguous_payload():
    source = b"head" + b"payload" + b"tail"
    assert patch.splice(source, b"payload", b"PAYLOAD") == b"headPAYLOADtail"
    with pytest.raises(patch.PatchError):
        patch.splice(b"payload" * 2, b"payload", b"PAYLOAD")
    with pytest.raises(patch.PatchError):
        patch.splice(b"head\n", b"head", b"h")
