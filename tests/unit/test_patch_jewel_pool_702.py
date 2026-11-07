import importlib.util
import json
import struct
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "patch_jewel_pool_702.py"
SPEC = importlib.util.spec_from_file_location("patch_jewel_pool_702", TOOL)
assert SPEC is not None and SPEC.loader is not None
sys.path.insert(0, str(TOOL.parent))
patch = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = patch
SPEC.loader.exec_module(patch)

CATALOG = json.loads((TOOL.parents[1] / "src" / "x2server" / "data" / "wish_catalog.json")
                     .read_text(encoding="utf-8"))


def table(entries):
    """Key/row array plaintext: 4-byte count, all keys, then all rows."""
    out = bytearray(len(entries).to_bytes(4, "little"))
    for key, _ in entries:
        out += patch._varint(1 << 3) + patch._varint(key)
    for _, row in entries:
        out += b"\x12" + patch._varint(len(row)) + row
    return bytes(out)


def make_row(*fields):
    return b"".join(patch._field(number, value) for number, value in fields)


def test_varint_and_field_encoding_are_readable():
    for value in (0, 1, 127, 128, 300, 22702, 1251004, 1 << 20):
        encoded = patch._varint(value)
        back, position = patch.read_varint(encoded, 0)
        assert back == value and position == len(encoded)
    assert patch._field(35, 1251004) == patch._varint(35 << 3) + patch._varint(1251004)


def test_quad_mesh_matches_the_verified_texture_orientation():
    data = patch.quad_mesh(688.0, 828.0)
    assert len(data) == 80
    vertices = [struct.unpack("<fffff", data[i * 20:i * 20 + 20]) for i in range(4)]
    assert [(round(v[0], 3), round(v[1], 3), round(v[3], 3), round(v[4], 3))
            for v in vertices] == [
        (-3.44, 4.14, 0.0, 1.0), (3.44, 4.14, 1.0, 1.0),
        (-3.44, -4.14, 0.0, 0.0), (3.44, -4.14, 1.0, 0.0)]
    assert patch.QUAD_INDEX_BUFFER == [0, 0, 1, 0, 2, 0, 2, 0, 1, 0, 3, 0]


def test_hashed_render_key_is_stable_and_distinct():
    first = patch.hashed_render_key("uialtas/drawing/jewel/baoshiji_2")
    assert len(first) == 4 and all(isinstance(word, int) for word in first)
    assert first == patch.hashed_render_key("uialtas/drawing/jewel/baoshiji_2")
    assert first != patch.hashed_render_key("uialtas/draw/guanggaotu_cover702")
    for piece in patch.PIECES:
        assert piece.container_key == piece.container_key.lower()


def test_split_and_build_array_are_inverse():
    entries = [(22702, make_row((1, 22702), (2, 2))),
               (750106, make_row((1, 750106), (2, 2)))]
    plain = table(entries)
    count, keys, rows, spans, keys_end = patch.split_array(plain)
    assert count == 2 and keys == [22702, 750106]
    assert rows == [row for _, row in entries]
    assert spans == sorted(spans)
    assert patch.build_array(plain, keys_end, rows) == plain


def test_split_array_refuses_malformed_framing():
    with pytest.raises(patch.PatchError):
        patch.split_array(b"\x01\x00\x00\x00" + patch._varint(1 << 3) + patch._varint(7))


def test_draw_param_row_gets_the_new_preview_jewel_after_f33():
    row = make_row((1, 22702), (2, 2), (4, 925), (4, 1), (33, 4310022), (37, 100), (38, 1))
    patched, description = patch.edit_draw_param_row(row)
    fields = patch._fields(patched)
    assert [field.field for field in fields] == [1, 2, 4, 4, 33, 35, 37, 38]
    assert [field.value for field in fields if field.field == 35] == [1251004]
    assert "f36" in description
    with pytest.raises(patch.PatchError, match="already has f35"):
        patch.edit_draw_param_row(patched)


def test_draw_rules_row_gets_the_up_jewel_and_pool_head():
    row = make_row((1, 22702), (2, 4310203), (5, 1251014), (5, 1251024), (7, 4310204))
    patched, description = patch.edit_draw_rules_row(row)
    fields = patch._fields(patched)
    numbers = [field.field for field in fields]
    assert numbers[:4] == [1, 2, 3, 5]
    assert [field.value for field in fields if field.field == 3] == [1251004]
    assert [field.value for field in fields if field.field == 5] == [1251004, 1251014, 1251024]
    assert "f3" in description and "f5" in description
    with pytest.raises(patch.PatchError, match="already has f3"):
        patch.edit_draw_rules_row(patched)


def test_top_gift_prepends_the_half_rate_six_star():
    row = make_row((1, 750108), (2, 2), (3, 80), (3, 70),
                   (4, 1251014), (4, 1251024), (5, 1), (7, 1))
    patched, description = patch.edit_gift_row(row, 750108)
    fields = patch._fields(patched)
    weights = [field.value for field in fields if field.field == 3]
    items = [field.value for field in fields if field.field == 4]
    assert weights == [496, 80, 70] and items == [1251004, 1251014, 1251024]
    assert weights[items.index(1251004)] == patch.TOP_WEIGHT
    assert "head" in description
    with pytest.raises(patch.PatchError, match="already lists"):
        patch.edit_gift_row(patched, 750108)


def test_common_gift_inserts_weight_and_item_before_the_anchor():
    row = make_row((1, 750106), (2, 2), (3, 1103), (3, 61), (3, 16),
                   (4, 1202023), (4, 1251014), (4, 1251024), (5, 1), (7, 1))
    patched, description = patch.edit_gift_row(row, 750106)
    fields = patch._fields(patched)
    weights = [field.value for field in fields if field.field == 3]
    items = [field.value for field in fields if field.field == 4]
    assert weights == [1103, 52, 61, 16]
    assert items == [1202023, 1251004, 1251014, 1251024]
    assert weights[items.index(1251004)] == patch.COMMON_WEIGHT
    assert "before 1251014" in description
    with pytest.raises(patch.PatchError, match="already lists"):
        patch.edit_gift_row(patched, 750106)


def test_gift_rejects_an_unpaired_or_missing_anchor():
    unpaired = make_row((1, 750106), (2, 2), (3, 1103), (4, 1202023), (4, 1251014))
    with pytest.raises(patch.PatchError, match="not paired"):
        patch.edit_gift_row(unpaired, 750106)
    missing = make_row((1, 750106), (2, 2), (3, 1103), (3, 61),
                       (4, 1202023), (4, 1251024))
    with pytest.raises(patch.PatchError, match="1251014 anchor"):
        patch.edit_gift_row(missing, 750106)


def test_container_group_insertion_keeps_keys_sorted_for_new_and_existing_groups():
    container = [("a", {"m_FileID": 1, "m_PathID": 10}),
                 ("uialtas/altas/draw", {"m_FileID": 2, "m_PathID": 20}),
                 ("uialtas/altas/draw", {"m_FileID": 2, "m_PathID": 21}),
                 ("z", {"m_FileID": 3, "m_PathID": 30})]
    position, placement = patch.insert_container_group(
        container, "uialtas/drawing/jewel/baoshiji_2", 4, (1000, 1001))
    assert placement == "new" and position == 3
    keys = [name for name, _ in container]
    assert keys == sorted(keys) and keys[3:5] == ["uialtas/drawing/jewel/baoshiji_2"] * 2
    position, placement = patch.insert_container_group(
        container, "uialtas/altas/draw", 2, (1002, 1003))
    assert placement == "existing" and position == 3
    keys = [name for name, _ in container]
    assert keys == sorted(keys)
    assert [value["m_PathID"] for name, value in container
            if name == "uialtas/altas/draw"] == [20, 21, 1002, 1003]


def test_container_insertion_refuses_a_misplaced_existing_block():
    container = [("uialtas/altas/draw", {"m_FileID": 1, "m_PathID": 1}),
                 ("uialtas/altas/draw", {"m_FileID": 1, "m_PathID": 2}),
                 ("uialtas/altas", {"m_FileID": 1, "m_PathID": 3})]
    with pytest.raises(patch.PatchError, match="not followed by a greater key"):
        patch.insert_container_group(container, "uialtas/altas/draw", 1, (1000, 1001))


def test_split_raw_text_asset_reads_the_binary_framing():
    name, script = b"Gift", bytes(range(64))
    raw = bytearray(len(name).to_bytes(4, "little") + name)
    raw += b"\x00" * (-len(raw) % 4)
    raw += len(script).to_bytes(4, "little") + script
    head, recovered = patch.split_raw_text_asset(bytes(raw), "Gift")
    assert recovered == script
    assert bytes(raw)[:len(head)] == head
    with pytest.raises(patch.PatchError):
        patch.split_raw_text_asset(bytes(raw), "DrawParam")


def test_split_raw_text_asset_refuses_a_truncated_script():
    name, script = b"DrawRules", bytes(range(8))
    raw = bytearray(len(name).to_bytes(4, "little") + name)
    raw += b"\x00" * (-len(raw) % 4)
    raw += (len(script) + 4).to_bytes(4, "little") + script
    with pytest.raises(patch.PatchError, match="runs past"):
        patch.split_raw_text_asset(bytes(raw), "DrawRules")


def test_bundled_art_has_the_published_sizes():
    expected = {
        "baoshiji_2_688x828.png": (688, 828),
        "cover702_1404x592.png": (1404, 592),
        "tab702_220x68.png": (220, 68),
    }
    for name, (width, height) in expected.items():
        path = patch.DEFAULT_ART_DIR / name
        assert path.is_file()
        assert patch.read_png_size(path) == (width, height)


def test_catalog_matches_the_gift_table_weights():
    groups = CATALOG["22702"]["groups"]
    common = {item["item_id"]: item for item in groups["common"]}
    top = {item["item_id"]: item for item in groups["top"]}
    assert common[1251004]["weight"] == patch.COMMON_WEIGHT == 52
    assert top[1251004]["weight"] == patch.TOP_WEIGHT == 496
    assert groups["top"][0]["item_id"] == 1251004
    assert groups["common"][15]["item_id"] == 1251004
    assert sum(item["weight"] for item in groups["top"]) == 992
    assert 0.0045 < 52 / sum(item["weight"] for item in groups["common"]) < 0.0055
    assert 0.45 < 496 / sum(item["weight"] for item in groups["top"]) < 0.55
