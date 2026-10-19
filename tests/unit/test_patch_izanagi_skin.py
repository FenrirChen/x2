import importlib.util
import struct
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "patch_izanagi_skin.py"
SPEC = importlib.util.spec_from_file_location("patch_izanagi_skin", TOOL)
assert SPEC is not None and SPEC.loader is not None
sys.path.insert(0, str(TOOL.parent))
patch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch)


def table(entries):
    """Appearance / UnitBase plaintext: 4-byte count, then all keys, then all rows."""
    out = bytearray(len(entries).to_bytes(4, "little"))
    for key, _ in entries:
        out += patch.varint(1 << 3) + patch.varint(key)
    for _, row in entries:
        out += patch.varint(2 << 3 | 2) + patch.varint(len(row)) + row
    return bytes(out)


def test_varint_runs_are_reversible():
    for value in (0, 1, 127, 128, 300, 1223003, 1 << 20):
        encoded = patch.varint(value)
        back, position = patch.read_varint(encoded, 0)
        assert back == value
        assert position == len(encoded)


def test_texture_rect_flips_a_top_origin_crop_box():
    # 1980x2048 painting; the shop card box is (x0, y0, x1, y1) in image coordinates.
    assert patch.texture_rect((878, 720, 1142, 1320), 2048) == (878, 728, 264, 600)
    assert patch.texture_rect((860, 720, 1200, 1060), 2048) == (860, 988, 340, 340)
    assert patch.HEAD_ICON_SIZE == 150


def test_quad_mesh_reproduces_the_shipped_sprite_ordering():
    data = patch.quad_mesh(150.0, 150.0)
    assert len(data) == 80
    vertices = [struct.unpack("<fffff", data[i * 20:i * 20 + 20]) for i in range(4)]
    assert [(round(v[0], 3), round(v[1], 3)) for v in vertices] == [
        (0.75, -0.75), (-0.75, -0.75), (-0.75, 0.75), (0.75, 0.75)]
    # The game's own quads carry an all-zero UV channel (the engine derives it
    # from textureRect / uvTransform); see SkinHead01 sprites.
    assert all(v[3] == 0.0 and v[4] == 0.0 for v in vertices)
    assert patch.QUAD_INDEX_BUFFER == [1, 0, 2, 0, 3, 0, 0, 0, 1, 0, 3, 0]


def test_render_tail_steps_past_the_maximum():
    assert patch.RENDER_TAIL_STEP == 2
    assert patch.render_tail([]) == 21300000
    assert patch.render_tail([21300000, 21300002]) == 21300004
    assert patch.render_tail([21300068]) == 21300070


def test_hashed_render_key_is_stable_and_distinct_per_container_key():
    first = patch.hashed_render_key(patch.DRAWING_KEY)
    assert len(first) == 4 and all(isinstance(word, int) for word in first)
    assert first == patch.hashed_render_key(patch.DRAWING_KEY)
    assert first != patch.hashed_render_key(patch.HALF_ICON_KEY)
    assert not any(any(ch.isupper() for ch in key)
                   for key in (patch.DRAWING_KEY, patch.HALF_ICON_KEY, patch.ATLAS_GROUP))


def test_split_and_build_array_are_inverse():
    entries = [(1030, patch.varint(48 << 3) + patch.varint(1223001)),
               (1223003, patch.varint(29 << 3) + patch.varint(55))]
    plain = table(entries)
    count, keys, rows, spans, keys_end = patch.split_array(plain)
    assert count == 2
    assert keys == [1030, 1223003]
    assert rows == [row for _, row in entries]
    assert spans == sorted(spans)
    assert patch.build_array(plain, keys_end, rows) == plain


def test_split_array_refuses_a_malformed_framing():
    with pytest.raises(patch.PatchError):
        patch.split_array(b"\x01\x00\x00\x00" + patch.varint(1 << 3) + patch.varint(7))


def test_field_span_locates_a_unique_field():
    row = (patch.varint(15 << 3 | 2) + patch.varint(3) + b"abc"
           + patch.varint(29 << 3) + patch.varint(110))
    start, end, value = patch.field_span(row, 15, 2)
    assert value == b"abc"
    assert row[start:end] == patch.varint(15 << 3 | 2) + patch.varint(3) + b"abc"
    _, _, value = patch.field_span(row, 29, 0)
    assert value == 110


def test_field_span_rejects_duplicate_or_wrong_wire_fields():
    row = (patch.varint(29 << 3) + patch.varint(1)
           + patch.varint(29 << 3) + patch.varint(2))
    with pytest.raises(patch.PatchError):
        patch.field_span(row, 29, 0)
    with pytest.raises(patch.PatchError):
        patch.field_span(row, 29, 2)
    with pytest.raises(patch.PatchError):
        patch.field_span(row, 48, 0)


def test_split_raw_text_asset_reads_the_binary_framing():
    name, script = b"Appearance", bytes(range(64))
    raw = bytearray(len(name).to_bytes(4, "little") + name)
    raw += b"\x00" * (-len(raw) % 4)
    raw += len(script).to_bytes(4, "little") + script
    head, recovered = patch.split_raw_text_asset(bytes(raw), "Appearance")
    assert recovered == script
    assert bytes(raw)[:len(head)] == head
    with pytest.raises(patch.PatchError):
        patch.split_raw_text_asset(bytes(raw), "UnitBase")


def test_split_raw_text_asset_refuses_a_truncated_script():
    name, script = b"UnitBase", bytes(range(8))
    raw = bytearray(len(name).to_bytes(4, "little") + name)
    raw += b"\x00" * (-len(raw) % 4)
    raw += (len(script) + 4).to_bytes(4, "little") + script  # declared longer than present
    with pytest.raises(patch.PatchError):
        patch.split_raw_text_asset(bytes(raw), "UnitBase")
