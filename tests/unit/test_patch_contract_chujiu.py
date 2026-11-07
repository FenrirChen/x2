import importlib.util
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "patch_contract_chujiu.py"
SPEC = importlib.util.spec_from_file_location("patch_contract_chujiu", TOOL)
assert SPEC is not None and SPEC.loader is not None
sys.path.insert(0, str(TOOL.parent))
patch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch)

# 2.4 基包 FavorabilityDate 的 128-byte RSA 头; 只用来验证头解析, 不依赖 APK。
RSA_BLOCK = bytes.fromhex(
    "03a2faa06d6518a38bf992dd37411fd03421c07184ce55f5b4cc35d2dde31f1a"
    "02f80174a28657e77c5b8730be54f09966270962dba552ed1e0fdb87ec9f507e"
    "a85b61309ddc55e4c637a834f8dd58ef9571f4083ad8f913962630ef20df2e97"
    "bc1c0c7a7f4750c0480aadea4a3b5cf3f970f952abe8de5bfc3a1d1aa1b4be65")
RSA_MESSAGE = bytes.fromhex(
    "64f6f8000a308f060dce8f0208cf8f0604d08f0608b1901708b2900608b3900613b49006"
    "08959106089691060897b8060898910608f9910608fa910608fb910632fc9106"
    "08dd920608de920608df920608e0920608c1930608c29306089a930608c49306")


def table(entries):
    """4-byte count + 全部 key + 全部 row。"""
    out = bytearray(len(entries).to_bytes(4, "little"))
    for key, _ in entries:
        out += patch.f_int(1, key)
    for _, row in entries:
        out += patch.tag(2, 2) + patch.varint(len(row)) + row
    return bytes(out)


def test_varint_runs_are_reversible():
    for value in (0, 1, 127, 128, 300, 13430051, 1 << 20, -1, -500):
        encoded = patch.varint(value)
        back, position = patch.read_varint(encoded, 0)
        assert back == (value if value >= 0 else value + (1 << 64))
        assert position == len(encoded)


def test_message_fields_round_trip_keeps_order_and_wire_types():
    row = (patch.f_int(1, 101001) + patch.f_int(2, 12) + patch.f_int(3, 1010)
           + patch.f_str(5, "UIAltas/CG/meishijie_yuehui") + patch.f_int(6, -500)
           + patch.f_int(7, 2141001) + patch.f_int(8, 1))
    fields = patch.message_fields(row)
    assert [number for number, _ in fields] == [1, 2, 3, 5, 6, 7, 8]
    assert fields[4] == (6, (1 << 64) - 500)
    assert fields[3] == (5, b"UIAltas/CG/meishijie_yuehui")
    assert patch.message_dict(row)[7] == [2141001]


def test_table_parse_and_serialize_are_inverse():
    entries = [
        (101001, patch.f_int(1, 101001) + patch.f_int(3, 1010)),
        (101002, patch.f_int(1, 101002) + patch.f_int(3, 1010)),
    ]
    plain = table(entries)
    keys, rows = patch.parse_table(plain)
    assert keys == [key for key, _ in entries]
    assert rows == [row for _, row in entries]
    assert patch.serialize_table(keys, rows) == plain


def test_parse_table_rejects_malformed_framing():
    with pytest.raises(patch.PatchError):
        patch.parse_table(b"\x01\x00\x00\x00" + patch.f_int(1, 7))
    entries = [(7, patch.f_int(1, 7))]
    with pytest.raises(patch.PatchError):
        patch.parse_table(table(entries) + b"\x00")
    with pytest.raises(patch.PatchError):
        patch.parse_table(b"\x02\x00\x00\x00" + patch.f_int(1, 7))


def test_insert_sorted_keeps_the_key_array_ordered():
    keys, rows = [1, 5], [b"a", b"b"]
    patch.insert_sorted(keys, rows, [(3, b"c"), (7, b"d")])
    assert keys == [1, 3, 5, 7]
    assert rows == [b"a", b"c", b"b", b"d"]
    with pytest.raises(patch.PatchError):
        patch.insert_sorted(keys, rows, [(3, b"dup")])


def test_split_raw_text_asset_reads_the_binary_framing():
    name, script = b"FavorabilityDate", bytes(range(64))
    raw = bytearray(len(name).to_bytes(4, "little") + name)
    raw += b"\x00" * (-len(raw) % 4)
    raw += len(script).to_bytes(4, "little") + script
    head, recovered = patch.split_raw_text_asset(bytes(raw), "FavorabilityDate")
    assert recovered == script
    assert bytes(raw)[:len(head)] == head
    with pytest.raises(patch.PatchError):
        patch.split_raw_text_asset(bytes(raw), "Language")


def test_split_raw_text_asset_refuses_a_truncated_script():
    name, script = b"Language", bytes(range(8))
    raw = bytearray(len(name).to_bytes(4, "little") + name)
    raw += b"\x00" * (-len(raw) % 4)
    raw += (len(script) + 4).to_bytes(4, "little") + script
    with pytest.raises(patch.PatchError):
        patch.split_raw_text_asset(bytes(raw), "Language")


def test_rsa_header_parsing_matches_the_reference_block():
    assert patch.rsa_public_unpad(RSA_BLOCK) == RSA_MESSAGE
    with pytest.raises(ValueError):
        patch.rsa_public_unpad(RSA_BLOCK[:127])
    with pytest.raises(ValueError):
        patch.rsa_public_unpad(b"\x00" * 128)


def test_decode_table_script_passes_plaintext_through():
    plain = table([(19, patch.f_int(1, 19))])
    recovered, already = patch.decode_table_script(plain, "FavorabilityLevel")
    assert recovered == plain
    assert already is True


def test_bl_and_b_encoding_points_back_at_the_target():
    for opcode, build in ((0x94000000, patch.bl_insn), (0x14000000, patch.b_insn)):
        word = build(0x1B4A0C4, 0x42B3AD8)
        assert word & 0xFC000000 == opcode
        assert patch.branch_target(word, 0x1B4A0C4) == 0x42B3AD8
        backward = build(0x42B3AD8, 0x1B4A0C4)
        assert patch.branch_target(backward, 0x42B3AD8) == 0x1B4A0C4
    with pytest.raises(patch.PatchError):
        patch.b_insn(0x1000, 0x1000 + (1 << 27))


def test_signature_matches_requires_a_full_prefix():
    signature = bytes.fromhex("2700000008eb0708ec0708ed0708ee07")
    assert patch.signature_matches(signature + b"\x00", signature)
    assert patch.signature_matches(signature, signature)
    assert not patch.signature_matches(signature[:-1], signature)
    assert not patch.signature_matches(b"", signature)
    assert not patch.signature_matches(signature, b"")


def test_chip_id_covers_chujiu_and_the_far_hero():
    assert patch.chip_id(1010, 1) == 2141001
    assert patch.chip_id(1010, 18) == 2141018
    assert patch.chip_id(1199, 18) == 21419918
    assert patch.CHUJIU_DATES[101001]["chips"][0] == 2141001
    assert patch.CHUJIU_DATES[101002]["chips"][-1] == 2141018


def test_chujiu_date_row_keeps_the_old_package_field_order():
    row = patch._chujiu_date_row(101001)
    assert [number for number, _ in patch.message_fields(row)] == (
        [1, 2, 3, 4, 5, 6, 6, 8] + [7] * 9)
    data = patch.message_dict(row)
    assert data[4] == [1710200]
    assert data[5] == [b"UIAltas/CG/meishijie_yuehui"]
    assert data[6] == [565, 30]
    assert data[8] == [1]


def test_hero_and_level_edits_are_idempotent():
    rows = [patch.f_int(1, hero) + patch.f_int(3, 20) for hero in patch.HEROES]
    keys = list(patch.HEROES)
    before = list(rows)
    _, after, _ = patch.edit_hero(keys, rows)
    assert after == before
    with pytest.raises(patch.PatchError):
        patch.edit_hero(list(patch.HEROES),
                        [patch.f_int(1, hero) + patch.f_int(3, 15) for hero in patch.HEROES])

    level = patch.f_int(1, 19) + patch.f_int(2, 10)
    keys, rows = [19], [level]
    patch.edit_level(keys, rows)
    patched = rows[0]
    patch.edit_level(keys, rows)
    assert rows[0] == patched
    assert patch.message_dict(patched)[6] == [1]
    assert patch.message_dict(patched)[7] == [1204011, 1]


def test_make_detail_image_pads_and_crops_to_the_sheet_size():
    Image = pytest.importorskip("PIL.Image")
    wide = Image.new("RGBA", (600, 800), (10, 20, 30, 255))
    assert patch.make_detail_image(wide).size == patch.DETAIL_SIZE
    narrow = Image.new("RGBA", (400, 800), (10, 20, 30, 255))
    assert patch.make_detail_image(narrow).size == patch.DETAIL_SIZE


def test_rescale_scene_frame_keeps_the_canvas_size():
    Image = pytest.importorskip("PIL.Image")
    source = Image.new("RGBA", (64, 48), (12, 34, 56, 255))
    canvas = patch.rescale_scene_frame(source, patch.MARRY_SCENE_RATIO)
    assert canvas.size == source.size
    assert canvas.mode == "RGBA"
    with pytest.raises(patch.PatchError):
        patch.rescale_scene_frame(source, 0.0)
    with pytest.raises(patch.PatchError):
        patch.rescale_scene_frame(source, 1.5)
