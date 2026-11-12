"""Restore the 契约(花嫁) system and 涂山初玖's contract look in the 2.4 client.

Build-time only.  The 2.4 client still ships the whole 约会 / 契约 code path
(``FavorDateModule``); the data and the art were switched off, not removed.  This
tool patches the reference APK so the server side (``src/x2server/player/date.py``
and ``favor.py``) has a matching client:

  * 25 神格 (1003..1024, 1197..1199) get two 约会 rows with all 18 契约碎片;
  * ``FavorabilityLevel`` 19 gains ``IsCovenant`` + 信物 ``1204011``, and the 25
    heroes' ``LevelLimit`` goes 10 -> 20;
  * 涂山初玖 (hero 1010) gets Appearance ``1221004`` (契约形象) + Item / Picture /
    ExpressionInteractiveArea / UnitBase rows;
  * five art bundles from the 1.0 package are re-attached and registered in the
    ``globalgamemanagers`` container;
  * ``libil2cpp.so`` gets a 16-byte-prefix plaintext bypass (the tables grow, so
    the 128-byte RSA header can no longer cover them), the 完成度 fix and the
    "only 1010 shows the 契约拼图" helper.

Three independent blocks, each self-checking:

  A. 表补丁  TextAsset ``m_Script`` is written as plaintext.  11 tables:
     FavorabilityHero / FavorabilityLevel / FavorabilityDate / OptionEffect /
     Appearance / Item / Picture / ExpressionInteractiveArea / UnitBase / Language /
     FunctionOpen (约会页签 OpenLevel 999 -> 1, 否则整个页签灰掉)。
     Every table keeps its original RSA head in ``m_Script`` but the payload is
     plain; the libil2cpp hook below lets ``ConvertDataBytes`` pass it through.
  B. 美术注入  The five bundles are byte-copies of the 1.0 package (same Unity
     2017.4f1 version), plus one extra 304x512 detail sprite in the 花嫁 bundle
     and the 0.66 scene rescale.  ``globalgamemanagers`` only grows (externals
     append + container insert), so every existing m_FileID stays valid.
  C. libil2cpp fixed offsets, each guarded by the original instruction:
     HOOK 0x1B4A0C4 (b OLD_CAVE) -> NEW_CAVE 0x42B3AD8, 完成度 bl at 0x1AAA334,
     and the two ``bl CheckMarried`` sites 0x1AA811C / 0x1AA87C0.

Only the APK is read.  Assets default to ``tools/assets/contract/`` next to this
script; outputs go to ``--output`` and are never written back into the input.

    python tools/patch_contract_chujiu.py --apk <reference.apk> --output <dir>

The output directory holds the replacement ``assets/bin/Data/*.bin`` /
``lib/arm64-v8a/libil2cpp.so.bin`` plus ``patches.json`` (zip entry -> file) and
``audit.json`` (per-change detail).  Resealing/signing is a separate step and is
not performed here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS / "analysis"))
from _client_table_wire import (  # noqa: E402
    WireError,
    convert_data_bytes,
    read_varint,
    rsa_public_unpad,
)

DATA_PREFIX = "assets/bin/Data/"
DEFAULT_ASSETS = TOOLS / "assets" / "contract"

HEROES = [1003, 1004, 1005, 1006, 1007, 1008, 1009, 1010, 1011, 1012, 1013, 1014,
          1015, 1016, 1017, 1018, 1019, 1020, 1021, 1022, 1023, 1024,
          1197, 1198, 1199]
CHUJIU = 1010
DATE_LEVELS = (12, 14)
DATE_POS = ((565, 30), (-300, 60))
DATE_CG = (
    "UIAltas/CG/meishijie_yuehui", "UIAltas/CG/modu_yuehui",
    "UIAltas/CG/modu2_yuehui", "UIAltas/CG/moduyewan_yuehui",
    "UIAltas/CG/moduyu_yuehui", "UIAltas/CG/moduhuanghun_yuehui",
    "UIAltas/CG/huoguodian_yuehui", "UIAltas/CG/jiedao_yuehui",
)
# 初玖旧包原行(2.4 基包里只剩 f1/f3/f8=2 的空壳, 所以这些值必须随工具提供)。
CHUJIU_DATES = {
    101001: {"level": 12, "talk": 1710200, "cg": "UIAltas/CG/meishijie_yuehui",
             "pos": (565, 30), "chips": tuple(range(2141001, 2141010))},
    101002: {"level": 14, "talk": 1710233, "cg": "UIAltas/CG/modu_yuehui",
             "pos": (-500, 60), "chips": tuple(range(2141010, 2141019))},
}
DATE_TALK = {
    1003: (1703004, 1703006), 1004: (1704005, 1704004), 1005: (1705006, 1705005),
    1006: (1706012, 1706021), 1007: (1707003, 1707006), 1008: (1708005, 1708004),
    1009: (1709006, 1709005), 1011: (1711002, 1711002), 1012: (1712002, 1712005),
    1013: (1713005, 1713004), 1014: (1714011, 1714009), 1015: (1715006, 1715005),
    1016: (1716010, 1716014), 1017: (1717004, 1717017), 1018: (1718018, 1718024),
    1019: (1719012, 1719010), 1020: (1720005, 1720004), 1021: (1721005, 1721004),
    1022: (1722005, 1722004), 1023: (1723005, 1723001), 1024: (1724003, 1724005),
    1197: (1797005, 1797004), 1198: (1798004, 1798006), 1199: (1799018, 1799016),
}
APPEARANCE = 1221004
ITEM_SKIN = 1221004
ITEM_HEAD = 1271004
PICTURE = 1271004
COVENANT_ITEM = 1204011
COVENANT_LEVEL_LIMIT = 20
DATE_FUNCTION_ID = 21946                     # FunctionOpen: FunctionType 36 = 约会
DATE_OPEN_LEVEL = 1                          # 约会页签开放等级; 内容仍由好感等级把关
TEMPLATE_APPEARANCE = 1221005
TEMPLATE_EIA = 1221003

TABLE_ENTRIES = {
    "FavorabilityHero": "0881faec387c4c54db57d59afa2d2ac7",
    "FavorabilityLevel": "8984f6d08589ea045ba79cbaa510bb4b",
    "FavorabilityDate": "5789c0845c7db484797bcc13b60a087e",
    "OptionEffect": "6efa934c9d8a41546b44787125f9730a",
    "Appearance": "2c6eecbf62e755847898fdb41e07d857",
    "Item": "e49ddfae661db9147b8823552f01df41",
    "Picture": "d83394ef195a71d46a11b5b5f680d7f5",
    "ExpressionInteractiveArea": "c5d172aa26318b84cb50ce61b36c684a",
    "UnitBase": "5c993e6912a40e541be49a4f5ed7abd7",
    "Language": "844762d28a77f85408b631eb3f0186bc",
    "FunctionOpen": "1b9954217ea8b6f44b8a31c89cf9edd7",
}

# 1.0 包里的美术文件 -> 要注册的容器键 / pathID。文件内容逐字节搬用, 不重序列化。
MARRY = "06d6762cd0bf8914c8b140e93fc5d846"
DETAIL_KEY = "uialtas/marrydrawing/marrydrawing_1221004_detail"
DETAIL_NAME = "MarryDrawing_1221004_Detail"
DETAIL_TEXTURE_PID, DETAIL_SPRITE_PID = 1000, 1001
DETAIL_SIZE = (304, 512)
MARRY_TEXTURE_PID = 1
MARRY_SCENE_RATIO = 0.66
ART = {
    "05a68fcce3dd15c4b80bc28ed86f9d33": [
        ("uialtas/altas/chujiu_marry", list(range(1, 20)))],
    "7baf99e6e7940604bb5a4ba44150959e": [
        ("uialtas/altas/covenant", [1, 2])],
    "5f3a0a68a4b8e7943a375fb814d67fc2": [
        ("uialtas/altas/marryhead01", [1, 2])],
    "d3b1e7dd001810a408e1412ab4903fa2": [
        ("uialtas/heroicon_h/hero_icon_101004_h", [1, 2])],
    MARRY: [
        ("uialtas/marrydrawing/marrydrawing_1221004", [1, 2]),
        (DETAIL_KEY, [DETAIL_TEXTURE_PID, DETAIL_SPRITE_PID])],
}
ART_WANT = {
    "05a68fcce3dd15c4b80bc28ed86f9d33": {1: "ChuJiu_marry"},
    "7baf99e6e7940604bb5a4ba44150959e": {1: "Covenant", 2: "Icon_1010"},
    "5f3a0a68a4b8e7943a375fb814d67fc2": {1: "MarryHead01", 2: "Hero_Icon_101004"},
    "d3b1e7dd001810a408e1412ab4903fa2": {1: "Hero_Icon_101004_H", 2: "Hero_Icon_101004_H"},
    MARRY: {1: "MarryDrawing_1221004", 2: "MarryDrawing_1221004"},
}
GG = "globalgamemanagers"
NATIVE = "lib/arm64-v8a/libil2cpp.so"

# C. libil2cpp: 固定偏移 + 原指令断言。基包若不匹配会在这里直接报错。
HOOK = 0x1B4A0C4
OLD_CAVE = 0x42B0D00
NEW_CAVE = 0x42B3AD8
ZERO_END = 0x42B4718
ORIGINAL = 0xA9BC5FF8
RET = 0xD65F03C0
EXPECTED_BASE_SIGS = (
    "1d00000008a10608a20608a30608a406",
    "8d00000008f1a20408f2a20408f3a204",
)
PCT_SITE = 0x1AAA334
PCT_FROM = 0x1AA5AE0
PCT_TO = 0x1AA59EC
CHECK_MARRIED = 0x1AA53BC
MARRIED_SITES = (0x1AA811C, 0x1AA87C0)

TEXTURE_CLASS, SPRITE_CLASS, RESOURCE_CLASS, TEXT_CLASS = 28, 213, 147, 49
QUAD_INDEX_BUFFER = [1, 0, 2, 0, 3, 0, 0, 0, 1, 0, 3, 0]
RENDER_TAIL_STEP = 2


class PatchError(RuntimeError):
    """The input APK / asset does not match the reference layout."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PatchError(message)


# ---------------------------------------------------------------- protobuf / 表
def varint(value: int) -> bytes:
    if value < 0:
        value += 1 << 64                      # protobuf int32 负数按 64 位补码编码
    out = bytearray()
    while True:
        part = value & 0x7F
        value >>= 7
        if value:
            out.append(part | 0x80)
        else:
            out.append(part)
            return bytes(out)


def tag(number: int, wire: int) -> bytes:
    return varint((number << 3) | wire)


def f_int(number: int, value: int) -> bytes:
    return tag(number, 0) + varint(value)


def f_str(number: int, value: str | bytes) -> bytes:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return tag(number, 2) + varint(len(raw)) + raw


def encode_field(number: int, value: int | bytes) -> bytes:
    return f_int(number, value) if isinstance(value, int) else f_str(number, value)


def message_fields(body: bytes) -> list[tuple[int, int | bytes]]:
    """[(field number, value)] 按出现顺序; wire 0 -> int, wire 2 -> bytes。"""
    out: list[tuple[int, int | bytes]] = []
    position = 0
    while position < len(body):
        try:
            raw_tag, position = read_varint(body, position)
        except WireError as exc:
            raise PatchError(f"bad field tag at {position}") from exc
        number, wire = raw_tag >> 3, raw_tag & 7
        if wire == 0:
            try:
                value, position = read_varint(body, position)
            except WireError as exc:
                raise PatchError(f"bad varint for field {number}") from exc
            out.append((number, value))
        elif wire == 2:
            try:
                length, position = read_varint(body, position)
            except WireError as exc:
                raise PatchError(f"bad length for field {number}") from exc
            end = position + length
            require(end <= len(body), f"field {number} runs past the row")
            out.append((number, bytes(body[position:end])))
            position = end
        else:
            raise PatchError(f"unsupported wire type {wire} for field {number}")
    return out


def message_dict(body: bytes) -> dict[int, list[int | bytes]]:
    out: dict[int, list[int | bytes]] = {}
    for number, value in message_fields(body):
        out.setdefault(number, []).append(value)
    return out


def parse_table(plain: bytes) -> tuple[list[int], list[bytes]]:
    """4B 行数 + 全部 f1 key + 全部 f2 行; 任何尾随字节都算结构不符。"""
    require(len(plain) >= 4, "table payload is shorter than its 4-byte count")
    count = int.from_bytes(plain[:4], "little")
    position = 4
    keys: list[int] = []
    while position < len(plain) and plain[position] == 8:
        try:
            key, position = read_varint(plain, position + 1)
        except WireError as exc:
            raise PatchError("bad table key varint") from exc
        keys.append(key)
    rows: list[bytes] = []
    while position < len(plain) and plain[position] == 0x12:
        try:
            length, position = read_varint(plain, position + 1)
        except WireError as exc:
            raise PatchError("bad table row length") from exc
        end = position + length
        require(end <= len(plain), "table row runs past the payload")
        rows.append(plain[position:end])
        position = end
    require(count == len(keys) == len(rows),
            f"table framing is not a key/row array ({count}/{len(keys)}/{len(rows)})")
    require(position == len(plain), f"table payload has {len(plain) - position} trailing bytes")
    return keys, rows


def serialize_table(keys: list[int], rows: list[bytes]) -> bytes:
    out = bytearray(len(keys).to_bytes(4, "little"))
    for key in keys:
        out += f_int(1, key)
    for row in rows:
        out += tag(2, 2) + varint(len(row)) + row
    return bytes(out)


def insert_sorted(keys: list[int], rows: list[bytes],
                  pairs: list[tuple[int, bytes]]) -> None:
    for key, row in pairs:
        require(key not in keys, f"duplicate table key {key}")
        position = 0
        while position < len(keys) and keys[position] < key:
            position += 1
        keys.insert(position, key)
        rows.insert(position, row)


def chip_id(hero: int, position: int) -> int:
    return int(f"214{hero - 1000}{position:02d}")


# ---------------------------------------------------------------- TextAsset 读写
def read_entry(apk: Path, entry: str) -> bytes:
    with zipfile.ZipFile(apk) as archive:
        try:
            return archive.read(DATA_PREFIX + entry)
        except KeyError as exc:
            raise PatchError(f"{apk} is missing {DATA_PREFIX}{entry}") from exc


def split_raw_text_asset(raw: bytes, table: str) -> tuple[bytes, bytes]:
    """TextAsset 原始对象 -> (name 头, m_Script)。

    布局: [4B m_Name 长度][m_Name][补齐到 4][4B m_Script 长度][m_Script]。
    不能走 read_typetree: UnityPy 会把 m_Script 当 utf-8 解码, 往返破坏密文。
    """
    require(len(raw) >= 8, "TextAsset object is too short")
    length = int.from_bytes(raw[:4], "little")
    require(4 + length <= len(raw), "TextAsset name runs past the object")
    name = raw[4:4 + length].decode("utf-8", "strict")
    require(name == table, f"expected a {table} TextAsset, got {name!r}")
    position = (4 + length + 3) // 4 * 4
    require(position + 4 <= len(raw), "TextAsset m_Script length is missing")
    size = int.from_bytes(raw[position:position + 4], "little")
    require(position + 4 + size <= len(raw), "m_Script runs past the object")
    return raw[:position], raw[position + 4:position + 4 + size]


def decode_table_script(script: bytes, table: str) -> tuple[bytes, bool]:
    """Return (plaintext, already_plaintext); 已打过补丁的表直接是明文。"""
    try:
        parse_table(script)
    except PatchError:
        pass
    else:
        return script, True
    require(len(script) >= 128, f"{table} script is shorter than the 128-byte RSA header")
    try:
        rsa_public_unpad(script[:128])       # 先解析密文头, 失败给出明确的版本错误
        plain = convert_data_bytes(script)
    except (ValueError, IndexError) as exc:
        raise PatchError(f"{table} is neither a plaintext table nor an RSA payload") from exc
    parse_table(plain)                       # 结构不符会抛 PatchError
    return plain, False


def signature_matches(payload: bytes, signature: bytes) -> bool:
    """libil2cpp 的 16 B 前缀旁路只认前缀; 长度不足必须视为不匹配。"""
    if not signature or len(payload) < len(signature):
        return False
    return payload[:len(signature)] == signature


# ---------------------------------------------------------------- 表编辑
def edit_hero(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    """FavorabilityHero.f3(LevelLimit) 10 -> 20; 只改有约会数据的 25 个神格。"""
    changed = 0
    for hero in HEROES:
        require(hero in keys, f"FavorabilityHero lacks hero {hero}")
        index = keys.index(hero)
        current = message_dict(rows[index]).get(3)
        if current == [COVENANT_LEVEL_LIMIT]:
            continue
        require(current == [10], f"FavorabilityHero {hero} LevelLimit is {current}, expected 10")
        out = bytearray()
        for number, value in message_fields(rows[index]):
            out += encode_field(number, COVENANT_LEVEL_LIMIT if number == 3 else value)
        rows[index] = bytes(out)
        changed += 1
    return keys, rows, f"FavorabilityHero 等级上限 10 -> 20 ({changed} 个神格改写)"


def edit_level(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    """FavorabilityLevel 19: IsCovenant=1 + CovenantItem=[1204011,1]。"""
    require(19 in keys, "FavorabilityLevel lacks row 19")
    index = keys.index(19)
    row = rows[index]
    data = message_dict(row)
    covenant = data.get(6)
    items = data.get(7)
    if covenant == [1] and items == [COVENANT_ITEM, 1]:
        return keys, rows, "FavorabilityLevel Lv19 已是契约行"
    require(covenant is None and items is None,
            f"FavorabilityLevel 19 already has f6={covenant} f7={items}")
    rows[index] = row + f_int(6, 1) + f_int(7, COVENANT_ITEM) + f_int(7, 1)
    return keys, rows, "FavorabilityLevel Lv19: IsCovenant=1, CovenantItem=[1204011,1]"


def edit_function_open(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    """FunctionOpen 21946 (FunctionType 36 = 约会): OpenLevel 999 -> 1。

    ``FavorDateTab_OnCheckTabOpen`` 里就是 ``GameAPI.IsClientFunctionClose(21946)``,
    OpenLevel 仍是 999 时整个约会页签灰掉, 点一下只弹「解神者等级到达 999 级开放」。
    约会本身的开放条件(好感 12/14)在 FavorabilityDate 里, 不受这个总开关影响。
    """
    require(DATE_FUNCTION_ID in keys, "FunctionOpen lacks row 21946 (约会)")
    index = keys.index(DATE_FUNCTION_ID)
    data = message_dict(rows[index])
    current = data.get(4)
    if current == [DATE_OPEN_LEVEL]:
        return keys, rows, f"FunctionOpen 21946 约会已开放 (OpenLevel={DATE_OPEN_LEVEL})"
    require(current == [999], f"FunctionOpen 21946 OpenLevel is {current}, expected 999")
    out = bytearray()
    for number, value in message_fields(rows[index]):
        out += encode_field(number, DATE_OPEN_LEVEL if number == 4 else value)
    rows[index] = bytes(out)
    return keys, rows, f"FunctionOpen 21946 约会 OpenLevel 999 -> {DATE_OPEN_LEVEL}"


def _date_row(date_id: int, hero: int, level: int, talk: int, cg: str,
               position: tuple[int, int], chips: tuple[int, ...]) -> bytes:
    out = bytearray()
    out += f_int(1, date_id)
    out += f_int(2, level)
    out += f_int(3, hero)
    out += f_int(4, talk)
    out += f_str(5, cg)
    for value in position:
        out += f_int(6, value)
    for value in chips:
        out += f_int(7, value)
    out += f_int(8, 1)
    return bytes(out)


def _chujiu_date_row(date_id: int) -> bytes:
    """旧包原行: f8 在碎片之前(其余字段顺序照抄旧包), 与现役补丁逐字节一致。"""
    spec = CHUJIU_DATES[date_id]
    out = bytearray()
    out += f_int(1, date_id)
    out += f_int(2, spec["level"])
    out += f_int(3, CHUJIU)
    out += f_int(4, spec["talk"])
    out += f_str(5, spec["cg"])
    for value in spec["pos"]:
        out += f_int(6, value)
    out += f_int(8, 1)
    for value in spec["chips"]:
        out += f_int(7, value)
    return bytes(out)


def edit_date(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    """25 个神格各 2 条约会; 初玖保留旧包剧本/背景/坐标, 其余复用 8 张 CG。"""
    changed = 0
    for position, hero in enumerate(HEROES):
        first, second = hero * 100 + 1, hero * 100 + 2
        for date_id in (first, second):
            require(date_id in keys, f"FavorabilityDate lacks row {date_id}")
        if hero == CHUJIU:
            for date_id in (first, second):
                desired = _chujiu_date_row(date_id)
                index = keys.index(date_id)
                if rows[index] == desired:
                    continue
                rows[index] = desired
                changed += 1
            continue
        for sequence, date_id in enumerate((first, second)):
            chips = tuple(chip_id(hero, n) for n in range(1 + sequence * 9, 10 + sequence * 9))
            desired = _date_row(date_id, hero, DATE_LEVELS[sequence],
                                DATE_TALK[hero][sequence],
                                DATE_CG[(position * 2 + sequence) % len(DATE_CG)],
                                DATE_POS[sequence], chips)
            index = keys.index(date_id)
            if rows[index] == desired:
                continue
            rows[index] = desired
            changed += 1
    return keys, rows, f"FavorabilityDate {changed} 条约会行改写(25 神格 × 2)"


def edit_option(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    """24 个非初玖神格: 18 条碎片效果 + 2 条约会选项。"""
    additions: list[tuple[int, bytes]] = []
    for hero in HEROES:
        if hero == CHUJIU:
            continue
        for position in range(1, 19):
            option_id = chip_id(hero, position)
            body = f_int(1, option_id) + f_int(2, 14) + f_int(3, hero) + f_int(4, position)
            additions.append((option_id, body))
        for sequence in range(1, 3):
            option_id = int(f"213{hero - 1000}{sequence:02d}")
            body = (f_int(1, option_id) + f_int(2, 13) + f_int(2, 11)
                    + f_int(3, hero) + f_int(3, 0)
                    + f_int(4, hero * 100 + sequence) + f_int(4, 0))
            additions.append((option_id, body))
    added = 0
    for option_id, body in additions:
        if option_id in keys:
            require(rows[keys.index(option_id)] == body,
                    f"OptionEffect {option_id} exists with unexpected content")
            continue
        insert_sorted(keys, rows, [(option_id, body)])
        added += 1
    return keys, rows, f"OptionEffect 新增 {added} 条(24 神格 × (18 碎片 + 2 约会选项))"


def _appearance_row(template: bytes) -> bytes:
    out = bytearray()
    for number, value in message_fields(template):
        if number == 1:
            value = APPEARANCE
        elif number == 2:
            value = 3                                  # 3 = 契约形象(旧包原值)
        elif number == 5:
            value = 12210041
        elif number == 6:
            value = 12210042
        elif number == 7:
            value = 12210043
        elif number == 8:
            value = 12210044
        elif number == 9:
            value = b"MarryHead01/Hero_Icon_101004"
        elif number == 10:
            value = b"HeroHeadQ01/Hero_Icon_Q_1010"
        elif number == 11:
            value = b"UIAltas/HeroIcon_H/Hero_Icon_101004_H"
        elif number == 12:
            # 详情页按 sprite.rect 像素铺满; 花嫁整图 1864x2048 直接填 f12 会放大 ~6 倍。
            value = b"UIAltas/MarryDrawing/MarryDrawing_1221004_Detail"
        elif number == 13:
            value = b"ExpressionAnim/ExpressionAnimImgSkin"
        elif number == 14:
            value = b""                                # 无 live2d
        elif number == 15:
            value = b""                                # 无 spine
        elif number == 16:
            value = b"UIAltas/MarryDrawing/MarryDrawing_1221004"
        elif number in (17, 18):
            value = CHUJIU
        elif number == 42:
            value = b"UIAltas/QDrawing/Q_1010"
        out += encode_field(number, value)
    return bytes(out)


def edit_appearance(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    """克隆 1221005(初玖泳装)成契约形象 1221004。"""
    require(TEMPLATE_APPEARANCE in keys, f"Appearance lacks template {TEMPLATE_APPEARANCE}")
    desired = _appearance_row(rows[keys.index(TEMPLATE_APPEARANCE)])
    if APPEARANCE in keys:
        require(rows[keys.index(APPEARANCE)] == desired,
                f"Appearance {APPEARANCE} already exists with unexpected content")
        return keys, rows, f"Appearance {APPEARANCE} 已存在"
    insert_sorted(keys, rows, [(APPEARANCE, desired)])
    return keys, rows, f"克隆 {TEMPLATE_APPEARANCE} -> 契约形象 {APPEARANCE}"


def _item_row(item_id: int, item_type: int, rarity: int, sequence: int,
              icon: str, name_fields: tuple[int, ...]) -> bytes:
    out = bytearray()
    out += f_int(1, item_id)
    out += f_int(2, item_id * 10 + 1)
    for extra in name_fields:
        out += f_int(extra, item_id * 10 + extra)      # 名称/描述语言 id
    out += f_int(5, 1)
    out += f_int(6, item_type)
    out += f_int(7, rarity)
    out += f_int(8, 1)
    out += f_int(9, 1)
    out += f_int(11, 1)
    out += f_int(21, sequence)
    out += f_int(22, item_id)
    out += f_str(24, icon)
    out += f_str(26, b"")
    out += f_int(28, 1)
    return bytes(out)


def edit_item(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    additions = [
        (ITEM_SKIN, _item_row(ITEM_SKIN, 17, 5, 18,
                              "MarryHead01/Hero_Icon_101004", (3, 4))),
        (ITEM_HEAD, _item_row(ITEM_HEAD, 22, 5, 19,
                              "MarryHead01/Hero_Icon_101004", ())),
    ]
    added = 0
    for item_id, body in additions:
        if item_id in keys:
            require(rows[keys.index(item_id)] == body,
                    f"Item {item_id} exists with unexpected content")
            continue
        insert_sorted(keys, rows, [(item_id, body)])
        added += 1
    return keys, rows, f"Item 新增 {added} 条(1221004 外观 + 1271004 花嫁头像)"


def edit_picture(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    body = (f_int(1, PICTURE) + f_int(2, 2)
            + f_str(4, "MarryHead01/Hero_Icon_101004") + f_int(5, 1))
    if PICTURE in keys:
        require(rows[keys.index(PICTURE)] == body,
                f"Picture {PICTURE} exists with unexpected content")
        return keys, rows, f"Picture {PICTURE} 已存在"
    insert_sorted(keys, rows, [(PICTURE, body)])
    return keys, rows, f"新增 Picture {PICTURE}(花嫁头像)"


def edit_eia(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    """互动热区沿用 1221003(skin) 的行, 只换主键 —— 缺字段会 NRE。"""
    require(TEMPLATE_EIA in keys, f"ExpressionInteractiveArea lacks {TEMPLATE_EIA}")
    template = message_dict(rows[keys.index(TEMPLATE_EIA)])
    out = bytearray()
    for number in [1, *sorted(n for n in template if n != 1)]:
        values = [APPEARANCE] if number == 1 else template[number]
        for value in values:
            out += encode_field(number, value)
    desired = bytes(out)
    if APPEARANCE in keys:
        require(rows[keys.index(APPEARANCE)] == desired,
                f"ExpressionInteractiveArea {APPEARANCE} exists with unexpected content")
        return keys, rows, f"ExpressionInteractiveArea {APPEARANCE} 已存在"
    insert_sorted(keys, rows, [(APPEARANCE, desired)])
    return keys, rows, f"克隆 {TEMPLATE_EIA} 热区 -> {APPEARANCE}"


def edit_unitbase(keys: list[int], rows: list[bytes]) -> tuple[list[int], list[bytes], str]:
    require(CHUJIU in keys, f"UnitBase lacks {CHUJIU}")
    index = keys.index(CHUJIU)
    listed = [value for number, value in message_fields(rows[index]) if number == 48]
    if APPEARANCE in listed:
        require(listed.count(APPEARANCE) == 1 and listed[-1] == APPEARANCE,
                f"UnitBase {CHUJIU} AppearanceList is {listed}")
        return keys, rows, f"UnitBase {CHUJIU} f48 已含 {APPEARANCE}"
    require(listed[-5:] == [1221001, 1221002, 1221003, 1221005, 1221006],
            f"UnitBase {CHUJIU} AppearanceList is {listed}")
    rows[index] = rows[index] + f_int(48, APPEARANCE)
    return keys, rows, f"UnitBase {CHUJIU} f48 += {APPEARANCE}"


def edit_language(keys: list[int], rows: list[bytes],
                  assets: Path) -> tuple[list[int], list[bytes], str]:
    """契约说明页文案(1.0 有、2.4 被裁掉)。"""
    payload = json.loads((assets / "language_13430051_54.json").read_text(encoding="utf-8"))
    texts = payload["rows"]
    added = 0
    for language_id in (13430051, 13430052, 13430053, 13430054):
        text = texts[str(language_id)]
        body = f_int(1, language_id)
        for number in range(2, 6):                   # f2..f5 = 简/繁/韩/日, 统一中文
            body += f_str(number, text)
        if language_id in keys:
            require(rows[keys.index(language_id)] == body,
                    f"Language {language_id} exists with unexpected content")
            continue
        insert_sorted(keys, rows, [(language_id, body)])
        added += 1
    return keys, rows, f"Language 补契约说明页文案 {added} 条(13430051..54)"


# ---------------------------------------------------------------- 表补丁入口
def patch_table(apk: Path, entry: str, table: str, edit,
                assets: Path) -> tuple[bytes, dict, bytes]:
    import UnityPy

    serialized = next(iter(UnityPy.load(read_entry(apk, entry)).files.values()))
    values = serialized.objects
    objects = list(values.values()) if isinstance(values, dict) else list(values)
    require(len(objects) == 1 and objects[0].class_id == TEXT_CLASS,
            f"{entry} is not a single TextAsset")
    head, script = split_raw_text_asset(objects[0].get_raw_data(), table)
    plain, already_plain = decode_table_script(script, table)
    keys, rows = parse_table(plain)
    before_rows = len(keys)
    if table == "Language":
        new_keys, new_rows, description = edit(keys, rows, assets)
    else:
        new_keys, new_rows, description = edit(keys, rows)
    new_plain = serialize_table(new_keys, new_rows)

    body = head + len(new_plain).to_bytes(4, "little") + new_plain
    objects[0].set_raw_data(body + b"\x00" * (-len(body) % 4))
    payload = serialized.save()

    # 自检: 回读 m_Script 与表结构, 并比对 shipped 的前缀 sig。
    check = next(iter(UnityPy.load(payload).files.values()))
    checked = (list(check.objects.values()) if isinstance(check.objects, dict)
               else list(check.objects))
    require(len(checked) == 1 and checked[0].class_id == TEXT_CLASS,
            f"{entry} lost its TextAsset")
    _, again = split_raw_text_asset(checked[0].get_raw_data(), table)
    require(again == new_plain, f"{entry} payload does not round trip")
    back_keys, back_rows = parse_table(again)
    require(back_keys == new_keys and back_rows == new_rows,
            f"{entry} rows do not round trip")
    signature = new_plain[:16]

    spec = json.loads((assets / "table_sigs.json").read_text(encoding="utf-8"))
    expected = next((item for item in spec if item["table"] == table), None)
    require(expected is not None, f"table_sigs.json has no {table} entry")
    require(expected["entry"] == entry,
            f"table_sigs.json entry for {table} is {expected['entry']}, expected {entry}")
    require(signature_matches(new_plain, bytes.fromhex(expected["sig"])) is True
            and len(bytes.fromhex(expected["sig"])) == 16,
            f"{table} signature {signature.hex()} != expected {expected['sig']}; "
            "the APK is not the reference build")
    record = {
        "table": table,
        "rows": [before_rows, len(new_keys)],
        "plain_bytes": [len(plain), len(new_plain)],
        "already_plaintext": already_plain,
        "sig": signature.hex(),
        "detail": description,
    }
    return payload, record, signature


def patch_tables(apk: Path, assets: Path) -> tuple[
        dict[str, bytes], list[tuple[str, bytes]], list[dict]]:
    made: dict[str, bytes] = {}
    signatures: list[tuple[str, bytes]] = []
    audit: list[dict] = []
    plan = [
        ("FavorabilityHero", edit_hero),
        ("FavorabilityLevel", edit_level),
        ("FavorabilityDate", edit_date),
        ("OptionEffect", edit_option),
        ("Appearance", edit_appearance),
        ("Item", edit_item),
        ("Picture", edit_picture),
        ("ExpressionInteractiveArea", edit_eia),
        ("UnitBase", edit_unitbase),
        ("Language", edit_language),
        ("FunctionOpen", edit_function_open),
    ]
    for table, edit in plan:
        entry = TABLE_ENTRIES[table]
        payload, record, signature = patch_table(apk, entry, table, edit, assets)
        made[entry] = payload
        signatures.append((table, signature))
        audit.append(record)
    return made, signatures, audit


# ---------------------------------------------------------------- A. 美术基础工具
def quad_mesh(width: float, height: float) -> bytes:
    """4 顶点 / 20 B 每顶点(位置 float32x3 + UV float32x2); UV 全 0 同原版。"""
    half_width, half_height = width / 200.0, height / 200.0
    out = bytearray()
    for x, y in ((half_width, -half_height), (-half_width, -half_height),
                 (-half_width, half_height), (half_width, half_height)):
        out += struct.pack("<fffff", x, y, 0.0, 0.0, 0.0)
    return bytes(out)


def hashed_render_key(path: str) -> list[int]:
    digest = hashlib.md5(path.encode("utf-8")).digest()  # noqa: S324 - 资源键, 非安全用途
    return [int.from_bytes(digest[i * 4:i * 4 + 4], "little") for i in range(4)]


def render_tail(keys: list[int]) -> int:
    return max(keys) + RENDER_TAIL_STEP if keys else 21300000


def load_serialized(blob: bytes):
    import UnityPy

    return next(iter(UnityPy.load(blob).files.values()))


def objects(serialized) -> list:
    values = serialized.objects
    return list(values.values()) if isinstance(values, dict) else list(values)


def serialise_tree(serialized, class_id: int, tree: dict) -> bytes:
    from UnityPy.helpers.Tpk import get_typetree_node
    from UnityPy.helpers.TypeTreeHelper import write_typetree
    from UnityPy.streams import EndianBinaryWriter

    node = get_typetree_node(class_id, serialized.version)
    writer = EndianBinaryWriter(endian=serialized.header.endian)
    write_typetree(tree, node, writer, serialized)
    return writer.bytes


def add_object(serialized, path_id: int, class_id: int, tree: dict) -> None:
    from UnityPy.enums import ClassIDType
    from UnityPy.files import ObjectReader

    type_id = next((index for index, item in enumerate(serialized.types)
                    if item.class_id == class_id), None)
    require(type_id is not None, f"serialized file has no class {class_id} template")
    serialized_type = serialized.types[type_id]
    raw = serialise_tree(serialized, class_id, tree)
    serialized.objects[path_id] = ObjectReader(
        serialized, None, path_id, type_id, serialized_type, class_id,
        ClassIDType(class_id), 0, len(raw), None, None, data=raw)


def texture_tree(template: dict, name: str, image) -> dict:
    from PIL import Image
    from UnityPy.enums import TextureFormat

    raw = image.convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes()
    tree = copy.deepcopy(template)
    tree["m_Name"] = name
    tree["m_Width"], tree["m_Height"] = image.size
    tree["m_CompleteImageSize"] = len(raw)
    tree["m_TextureFormat"] = int(TextureFormat.RGBA32)
    tree["m_ForcedFallbackFormat"] = int(TextureFormat.RGBA32)
    tree["m_MipCount"] = 1
    tree["m_ImageCount"] = 1
    tree["m_TextureDimension"] = 2
    tree["m_IsReadable"] = False
    tree["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
    tree["image data"] = raw
    return tree


def place_sprite(tree: dict, texture_pid: int, rect: tuple[int, int, int, int]) -> None:
    x, y, width, height = rect
    render_data = tree["m_RD"]
    tree["m_Rect"] = {"x": float(x), "y": float(y),
                      "width": float(width), "height": float(height)}
    tree["m_Offset"] = {"x": 0.0, "y": 0.0}
    render_data["texture"] = {"m_FileID": 0, "m_PathID": texture_pid}
    render_data["alphaTexture"] = {"m_FileID": 0, "m_PathID": 0}
    render_data["textureRect"] = {"x": float(x), "y": float(y),
                                  "width": float(width), "height": float(height)}
    render_data["textureRectOffset"] = {"x": 0.0, "y": 0.0}
    render_data["atlasRectOffset"] = {"x": -1.0, "y": -1.0}
    render_data["settingsRaw"] = 64
    render_data["uvTransform"] = {"x": 100.0, "y": x + width / 2.0,
                                  "z": 100.0, "w": y + height / 2.0}
    render_data["downscaleMultiplier"] = 1.0
    data = quad_mesh(width, height)
    render_data["m_VertexData"]["m_DataSize"] = data
    render_data["m_VertexData"]["m_VertexCount"] = 4
    render_data["m_IndexBuffer"] = list(QUAD_INDEX_BUFFER)
    submesh = render_data["m_SubMeshes"][0]
    submesh["firstByte"] = 0
    submesh["indexCount"] = len(QUAD_INDEX_BUFFER) // 2
    submesh["topology"] = 0
    submesh["baseVertex"] = 0
    submesh["firstVertex"] = 0
    submesh["vertexCount"] = 4
    submesh["localAABB"] = {"m_Center": {"x": 0.0, "y": 0.0, "z": 0.0},
                            "m_Extent": {"x": width / 200.0, "y": height / 200.0, "z": 0.0}}
    tree["m_PhysicsShape"] = [[{"x": -width / 200.0, "y": -height / 200.0},
                               {"x": width / 200.0, "y": -height / 200.0},
                               {"x": width / 200.0, "y": height / 200.0},
                               {"x": -width / 200.0, "y": height / 200.0}]]


def sprite_tree(template: dict, name: str, texture_pid: int,
                rect: tuple[int, int, int, int], key, tail: int) -> dict:
    tree = copy.deepcopy(template)
    tree["m_Name"] = name
    tree["m_Border"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0}
    tree["m_Pivot"] = {"x": 0.5, "y": 0.5}
    tree["m_Extrude"] = 1
    tree["m_IsPolygon"] = False
    tree["m_RenderDataKey"] = [
        dict(zip(("data[0]", "data[1]", "data[2]", "data[3]"), key, strict=True)), tail]
    tree["m_AtlasTags"] = []
    tree["m_SpriteAtlas"] = {"m_FileID": 0, "m_PathID": 0}
    place_sprite(tree, texture_pid, rect)
    return tree


# ---------------------------------------------------------------- B. 花嫁立绘加工
def make_detail_image(source):
    """从 1864x2048 花嫁整图裁出神格详情立绘: 缩到高 512, 水平居中裁 304 宽。"""
    from PIL import Image

    width, height = source.size
    target_width, target_height = DETAIL_SIZE
    scaled_width = max(target_width, int(round(width * target_height / float(height))))
    image = source.convert("RGBA").resize((scaled_width, target_height), Image.LANCZOS)
    if scaled_width <= target_width:
        canvas = Image.new("RGBA", DETAIL_SIZE, (0, 0, 0, 0))
        canvas.paste(image, ((target_width - scaled_width) // 2, 0))
        return canvas
    left = (scaled_width - target_width) // 2
    return image.crop((left, 0, left + target_width, target_height))


def rescale_scene_frame(source, ratio: float):
    """画布尺寸不变, 把画面缩到 ratio 居中, 四周用同图放大模糊铺底。"""
    from PIL import Image, ImageFilter

    require(0.0 < ratio <= 1.0, f"scene ratio must be in (0, 1], got {ratio}")
    width, height = source.size
    foreground_width = max(1, int(round(width * ratio)))
    foreground_height = max(1, int(round(height * ratio)))
    foreground = source.resize((foreground_width, foreground_height), Image.LANCZOS)
    zoom = source.resize((int(round(width / ratio)), int(round(height / ratio))), Image.LANCZOS)
    left, top = (zoom.width - width) // 2, (zoom.height - height) // 2
    background = zoom.crop((left, top, left + width, top + height)).filter(
        ImageFilter.GaussianBlur(48))
    # 底色整体提亮, 否则原图边角的深色家具会透过留白形成脏块。
    background = Image.blend(background, Image.new("RGBA", background.size, (250, 247, 244, 255)),
                             0.62)
    canvas = background.copy()
    canvas.paste(foreground, ((width - foreground_width) // 2,
                              (height - foreground_height) // 2), foreground)
    return canvas


def add_detail_sprite(path: Path) -> tuple[int, int]:
    """在花嫁立绘文件里追加详情用 Texture2D+Sprite(pid 1000/1001), 整文件重建。"""
    serialized = load_serialized(path.read_bytes())
    existing = objects(serialized)
    used = {obj.path_id for obj in existing}
    detail_pids = {DETAIL_TEXTURE_PID, DETAIL_SPRITE_PID}
    require(not used & detail_pids,
            f"{path.name} already uses detail pids {sorted(used & detail_pids)}")
    texture_template = next(obj.read_typetree() for obj in existing
                            if obj.class_id == TEXTURE_CLASS)
    sprite_template = next(obj.read_typetree() for obj in existing if obj.class_id == SPRITE_CLASS)
    source = next(obj for obj in existing if obj.class_id == TEXTURE_CLASS).parse_as_object().image
    detail = make_detail_image(source)
    tails = [obj.read_typetree()["m_RenderDataKey"][1] for obj in existing
             if obj.class_id == SPRITE_CLASS]
    add_object(serialized, DETAIL_TEXTURE_PID, TEXTURE_CLASS,
               texture_tree(texture_template, DETAIL_NAME, detail))
    add_object(serialized, DETAIL_SPRITE_PID, SPRITE_CLASS,
               sprite_tree(sprite_template, DETAIL_NAME, DETAIL_TEXTURE_PID,
                           (0, 0, DETAIL_SIZE[0], DETAIL_SIZE[1]),
                           hashed_render_key(DETAIL_KEY), render_tail(tails)))
    path.write_bytes(serialized.save())

    check = load_serialized(path.read_bytes())
    texture = next(obj for obj in objects(check) if obj.path_id == DETAIL_TEXTURE_PID)
    require(texture.parse_as_object().image.size == DETAIL_SIZE, "detail texture size mismatch")
    sprite = next(obj for obj in objects(check) if obj.path_id == DETAIL_SPRITE_PID)
    tree = sprite.read_typetree()
    require(tree["m_Name"] == DETAIL_NAME, f"detail sprite name is {tree['m_Name']!r}")
    render = tree["m_RD"]
    require(render["texture"] == {"m_FileID": 0, "m_PathID": DETAIL_TEXTURE_PID},
            "detail sprite is not bound to the detail texture")
    require(render["textureRect"] == {"x": 0.0, "y": 0.0,
                                      "width": float(DETAIL_SIZE[0]),
                                      "height": float(DETAIL_SIZE[1])},
            f"detail sprite textureRect is {render['textureRect']}")
    return detail.size


def rescale_marry_scene(path: Path, ratio: float) -> tuple[float, tuple[int, int], tuple[int, int]]:
    serialized = load_serialized(path.read_bytes())
    texture = next(obj for obj in objects(serialized)
                   if obj.class_id == TEXTURE_CLASS and obj.path_id == MARRY_TEXTURE_PID)
    tree = texture.read_typetree()
    source = texture.parse_as_object().image.convert("RGBA")
    width, height = source.size
    canvas_image = rescale_scene_frame(source, ratio)
    texture.set_raw_data(serialise_tree(
        serialized, TEXTURE_CLASS, texture_tree(tree, tree["m_Name"], canvas_image)))
    path.write_bytes(serialized.save())

    check = load_serialized(path.read_bytes())
    got = next(
        obj for obj in objects(check)
        if obj.class_id == TEXTURE_CLASS and obj.path_id == MARRY_TEXTURE_PID
    ).parse_as_object().image.size
    require(got == (width, height), f"花嫁贴图尺寸被改: {got}")
    content = (max(1, int(round(width * ratio))), max(1, int(round(height * ratio))))
    return ratio, (width, height), content


def probe(blob: bytes) -> tuple[str, dict[int, tuple[int, str]], int]:
    """(version, {pid: (class_id, name)}, externals 数)。"""
    import UnityPy

    serialized = next(iter(UnityPy.load(blob).files.values()))
    info: dict[int, tuple[int, str]] = {}
    for obj in objects(serialized):
        if obj.class_id == TEXTURE_CLASS:
            info[obj.path_id] = (TEXTURE_CLASS, obj.read_typetree()["m_Name"])
        elif obj.class_id == SPRITE_CLASS:
            info[obj.path_id] = (SPRITE_CLASS, obj.read_typetree()["m_Name"])
    return str(serialized.version), info, len(serialized.externals)


def patch_art(assets: Path, output: Path, ratio: float) -> tuple[dict[str, bytes], list[str]]:
    """5 个 bundle: 4 个原样拷贝, 花嫁文件追加详情立绘并缩放画面。"""
    made: dict[str, bytes] = {}
    audit: list[str] = []
    for entry, groups in ART.items():
        source = assets / (entry + ".bin")
        require(source.exists(), f"missing asset {source}")
        blob = source.read_bytes()
        target = output / (entry + ".bin")
        target.write_bytes(blob)
        if entry == MARRY:
            detail_size = add_detail_sprite(target)
            used_ratio, canvas, content = rescale_marry_scene(target, ratio)
            audit.append(f"{entry}: 追加详情立绘 {DETAIL_NAME} {detail_size[0]}x{detail_size[1]} "
                         f"(pid {DETAIL_TEXTURE_PID}/{DETAIL_SPRITE_PID}); 画面缩到 "
                         f"{used_ratio * 100:.0f}% (画布 {canvas[0]}x{canvas[1]} 不变, "
                         f"内容 {content[0]}x{content[1]})")
            blob = target.read_bytes()
        version, info, externals = probe(blob)
        require(externals == 0, f"{entry} has external references, cannot be copied")
        require(version == "2017.4f1", f"{entry} is Unity {version}, expected 2017.4f1")
        want = dict(ART_WANT[entry])
        if entry == "05a68fcce3dd15c4b80bc28ed86f9d33":
            for index in range(1, 19):
                want[index + 1] = f"ChuJiu_{index}"
        if entry == MARRY:
            want[DETAIL_TEXTURE_PID] = DETAIL_NAME
            want[DETAIL_SPRITE_PID] = DETAIL_NAME
        for path_id, name in want.items():
            require(path_id in info, f"{entry} lacks pid {path_id}")
            require(info[path_id][1] == name,
                    f"{entry} pid {path_id} is {info[path_id][1]!r}, expected {name!r}")
        for key, path_ids in groups:
            require(all(path_id in info for path_id in path_ids),
                    f"{entry} container key {key} has missing pids")
        require(1 in info and info[1][0] == TEXTURE_CLASS, f"{entry} has no texture pid 1")
        sprites = sum(1 for value in info.values() if value[0] == SPRITE_CLASS)
        audit.append(f"{entry}: {len(info)} 个对象(tex 1 + sprite {sprites}), "
                     f"version={version}, externals=0")
        made[entry] = blob
    return made, audit


def patch_global(apk: Path, art: dict[str, bytes]) -> tuple[bytes, list[str]]:
    """globalgamemanagers: externals 只追加, container 按全小写/严格有序插入。"""
    import UnityPy
    from UnityPy.helpers.Tpk import get_typetree_node
    from UnityPy.helpers.TypeTreeHelper import write_typetree
    from UnityPy.streams import EndianBinaryWriter

    raw = read_entry(apk, GG)
    serialized = next(iter(UnityPy.load(raw).files.values()))
    require(str(serialized.version) == "2017.4f1",
            f"globalgamemanagers is Unity {serialized.version}, expected 2017.4f1")
    manager = next((obj for obj in objects(serialized) if obj.class_id == RESOURCE_CLASS), None)
    require(manager is not None, "globalgamemanagers holds no ResourceManager")
    container = list(manager.read_typetree()["m_Container"])
    # Resource supplementation can append bindings. Restore lookup order while
    # retaining the order within every same-key group and every pointer.
    container.sort(key=lambda pair: pair[0])
    keys = [key for key, _ in container]
    require(not any(any(char.isupper() for char in key) for key in keys),
            "base container has uppercase keys")
    require(all(keys[index] <= keys[index + 1] for index in range(len(keys) - 1)),
            "base container is not sorted")
    require(len(serialized.externals) > 0, "globalgamemanagers has no externals")

    base_externals, base_container = len(serialized.externals), len(container)
    template = serialized.externals[-1]
    require(template.type == 0, "last external is not a kNonAssetType template")
    file_ids: dict[str, int] = {}
    appended = 0
    for entry in ART:
        hit = next((index for index, external in enumerate(serialized.externals)
                    if external.path == entry), None)
        if hit is None:
            external = copy.deepcopy(template)
            external.path = entry
            serialized.externals.append(external)
            appended += 1
            file_ids[entry] = len(serialized.externals)     # 1 基下标
        else:
            file_ids[entry] = hit + 1

    inserted: list[str] = []
    for entry, groups in ART.items():
        for key, path_ids in groups:
            existing = [value for name, value in container if name == key]
            if existing and all(value["m_FileID"] > 0 and
                    serialized.externals[value["m_FileID"] - 1].path in {
                        "x2_chujiu_marry_head.assets", "x2_chujiu_marry_half.assets",
                        "x2_chujiu_marry_drawing.assets"} for value in existing):
                # Replace only the earlier resource-only stand-ins for these
                # exact keys. Other resources and external IDs stay untouched.
                container = [(name, value) for name, value in container if name != key]
                existing = []
            if existing:
                require(len(existing) == len(path_ids),
                        f"container {key} has {len(existing)} entries, expected {len(path_ids)}")
                require([value["m_PathID"] for value in existing] == path_ids,
                        f"container {key} -> {[value['m_PathID'] for value in existing]}")
                require(all(value["m_FileID"] == file_ids[entry] for value in existing),
                        f"container {key} points at another external")
                continue
            current = [name for name, _ in container]
            position = next((index for index, name in enumerate(current) if name > key),
                            len(container))
            container[position:position] = [
                (key, {"m_FileID": file_ids[entry], "m_PathID": path_id})
                for path_id in path_ids
            ]
            inserted.append(f"索引 {position} 处插 {key} x{len(path_ids)} -> "
                            f"fileID={file_ids[entry]}({entry[:12]})")

    if appended or inserted:
        node = get_typetree_node(RESOURCE_CLASS, serialized.version)
        writer = EndianBinaryWriter(endian=serialized.header.endian)
        tree = manager.read_typetree()
        tree["m_Container"] = container
        write_typetree(tree, node, writer, serialized)
        manager.set_raw_data(writer.bytes)
        payload = serialized.save()
    else:
        payload = raw                                     # 已打过: 原样返回, 不重序列化

    check = next(iter(UnityPy.load(payload).files.values()))
    checked_container = next(obj for obj in objects(check)
                             if obj.class_id == RESOURCE_CLASS).read_typetree()["m_Container"]
    checked_keys = [key for key, _ in checked_container]
    require(len(check.externals) == len(serialized.externals),
            "external count changed by more than the appended files")
    require(checked_keys == sorted(checked_keys), "patched container is not sorted")
    require(not any(any(char.isupper() for char in key) for key in checked_keys),
            "patched container has uppercase keys")
    for entry, groups in ART.items():
        for key, path_ids in groups:
            values = [value for name, value in checked_container if name == key]
            require([value["m_PathID"] for value in values] == path_ids,
                    f"container {key} -> {[value['m_PathID'] for value in values]}, "
                    f"expected {path_ids}")
            file_id = values[0]["m_FileID"]
            require(check.externals[file_id - 1].path == entry,
                    f"container {key} points at {check.externals[file_id - 1].path!r}, "
                    f"expected {entry!r}")
    audit = [f"gg: container {base_container} -> {len(checked_container)} 条 "
             f"(新增 {len(inserted)} 个键 / {len(container) - base_container} 条目), "
             f"externals {base_externals} -> {len(check.externals)} (新增 {appended} 条, 只追加)"]
    audit.extend("   " + line for line in inserted)
    return payload, audit


# ---------------------------------------------------------------- C. libil2cpp
def branch_target(word: int, pc: int) -> int:
    offset = word & 0x03FFFFFF
    if offset & 0x02000000:
        offset -= 0x04000000
    return pc + (offset << 2)


def bl_insn(source: int, target: int) -> int:
    offset = (target - source) >> 2
    require(-(1 << 25) <= offset < (1 << 25), f"bl out of range: {source:#x} -> {target:#x}")
    return 0x94000000 | (offset & 0x3FFFFFF)


def b_insn(source: int, target: int) -> int:
    offset = (target - source) >> 2
    require(-(1 << 25) <= offset < (1 << 25), f"b out of range: {source:#x} -> {target:#x}")
    return 0x14000000 | (offset & 0x3FFFFFF)


def ldr_uoff(register: int, base: int, offset: int) -> int:
    require(offset % 8 == 0, f"ldr offset {offset:#x} is not 8-byte aligned")
    return 0xF9400000 | ((offset // 8) << 10) | (base << 5) | register


def ldr_lit(register: int, pc: int, target: int) -> int:
    offset = (target - pc) >> 2
    require(-(1 << 18) <= offset < (1 << 18),
            f"ldr literal out of range: {pc:#x} -> {target:#x}")
    return 0x58000000 | ((offset & 0x7FFFF) << 5) | register


def build_payload(signatures: list[bytes]) -> bytes:
    """明文前缀旁路: 读 [x1+0] -> [x8+0x18] >= 0x10, 再逐个 16 B 比较。"""
    count = len(signatures)
    tail = 6 + 9 * count
    fallback = NEW_CAVE + tail * 4
    literals = NEW_CAVE + (tail + 2) * 4
    words = [0] * (tail + 2)
    words[0] = 0xB4000001 | (((fallback - NEW_CAVE) // 4) << 5)           # cbz x1, fallback
    words[1] = ldr_uoff(8, 1, 0)                                         # ldr x8,[x1]
    words[2] = 0xB4000008 | (((fallback - (NEW_CAVE + 8)) // 4) << 5)     # cbz x8, fallback
    words[3] = 0xB9401909                                                # ldr w9,[x8,#0x18]
    words[4] = 0x7100413F                                                # cmp w9,#0x10
    words[5] = 0x54000003 | (((fallback - (NEW_CAVE + 20)) // 4) << 5)    # b.lo fallback
    for index in range(count):
        base = 6 + 9 * index
        nxt = (NEW_CAVE + (6 + 9 * (index + 1)) * 4) if index + 1 < count else fallback
        words[base + 0] = ldr_lit(10, NEW_CAVE + (base + 0) * 4, literals + index * 16)
        words[base + 1] = ldr_uoff(9, 8, 0x20)
        words[base + 2] = 0xEB0A013F                                     # cmp x9,x10
        words[base + 3] = 0x54000001 | (((nxt - (NEW_CAVE + (base + 3) * 4)) // 4) << 5)
        words[base + 4] = ldr_lit(10, NEW_CAVE + (base + 4) * 4, literals + index * 16 + 8)
        words[base + 5] = ldr_uoff(9, 8, 0x28)
        words[base + 6] = 0xEB0A013F
        words[base + 7] = 0x54000001 | (((nxt - (NEW_CAVE + (base + 7) * 4)) // 4) << 5)
        words[base + 8] = RET
    words[tail + 0] = ORIGINAL
    words[tail + 1] = b_insn(fallback + 4, HOOK + 4)
    payload = struct.pack(f"<{len(words)}I", *words)
    for signature in signatures:
        require(len(signature) == 16, f"signature is {len(signature)} B, expected 16")
        payload += signature
    return payload


def read_existing_signatures(native: bytes) -> tuple[list[bytes], int]:
    def word(index: int) -> int:
        require(0 <= OLD_CAVE + index * 4 <= len(native) - 4,
                "old cave extends past the native file")
        return struct.unpack_from("<I", native, OLD_CAVE + index * 4)[0]
    require(word(0) & 0xFF000000 == 0xB4000000,
            f"old cave does not hold the expected template: {word(0):08x}")
    index = 6
    while word(index) != ORIGINAL:
        require(word(index + 8) == RET, "old cave block does not end in RET")
        index += 9
    require(word(index) == ORIGINAL,
            f"old cave fallback is {word(index):08x}, expected {ORIGINAL:08x}")
    count = (index - 6) // 9
    # The local release has one prefix and a NOP before its literals; the PR's
    # reference has two prefixes and no padding. Decode LDR literal targets
    # instead of mistaking that NOP for the first four signature bytes.
    literals = []
    for position in range(6, index):
        insn = word(position)
        if insn & 0xFF00001F == 0x5800000A:
            offset = (insn >> 5) & 0x7FFFF
            if offset & 0x40000:
                offset -= 0x80000
            literals.append(OLD_CAVE + position * 4 + offset * 4)
    require(len(literals) == count * 2, "old cave literal count mismatch")
    signatures = []
    for first, second in zip(literals[::2], literals[1::2]):
        require(second == first + 8 and first >= OLD_CAVE + (index + 2) * 4,
                "old cave literal layout mismatch")
        signatures.append(native[first:second + 8])
    used = max(literals) + 8 - OLD_CAVE
    return signatures, used


def hide_marry_payload(helper: int) -> bytes:
    compare_chujiu = 0x7100001F | (CHUJIU << 10) | (1 << 5)   # cmp w1, #1010
    branch_equal = 0x54000000 | (3 << 5)                      # b.eq helper+16
    move_result = 0x52800020                                  # mov w0, #1
    return struct.pack("<5I", compare_chujiu, branch_equal, move_result, RET,
                       b_insn(helper + 16, CHECK_MARRIED))


def patch_date_percent(native: bytearray) -> str:
    """完成度改为「已收集碎片 / 碎片总数」; 幂等: 已打过就保留。"""
    current = struct.unpack_from("<I", native, PCT_SITE)[0]
    old, new = bl_insn(PCT_SITE, PCT_FROM), bl_insn(PCT_SITE, PCT_TO)
    require(current in (old, new),
            f"完成度补丁点 {PCT_SITE:#x} is {current:08x}, expected {old:08x}/{new:08x}")
    struct.pack_into("<I", native, PCT_SITE, new)
    return f"完成度补丁: {PCT_SITE:#x} {old:08x} -> {new:08x}"


def patch_hide_marry(native: bytearray, helper: int) -> list[str]:
    """两处 bl CheckMarried 改指向辅助函数; 非 1010 恒返回 1(已契约)。"""
    native[helper:helper + 20] = hide_marry_payload(helper)
    audit = []
    for site in MARRIED_SITES:
        current = struct.unpack_from("<I", native, site)[0]
        old, new = bl_insn(site, CHECK_MARRIED), bl_insn(site, helper)
        require(current in (old, new),
                f"契约拼图补丁点 {site:#x} is {current:08x}, expected {old:08x}/{new:08x}")
        struct.pack_into("<I", native, site, new)
        audit.append(f"隐藏契约拼图: {site:#x} {old:08x} -> {new:08x} (bl -> {helper:#x})")
    return audit


def patch_native(apk: Path, signatures: list[tuple[str, bytes]]) -> tuple[bytes, list[str]]:
    """libil2cpp: 组装前缀 payload + 完成度 + 契约拼图隐藏。重复运行不叠加。"""
    with zipfile.ZipFile(apk) as archive:
        native = bytearray(archive.read(NATIVE))
    hook_word = struct.unpack_from("<I", native, HOOK)[0]
    require(hook_word & 0xFC000000 in (0x14000000, 0x94000000),
            f"HOOK {HOOK:#x} is not a B/BL: {hook_word:08x}")
    hook_target = branch_target(hook_word, HOOK)
    require(hook_target in (OLD_CAVE, NEW_CAVE),
            f"HOOK {HOOK:#x} points at {hook_target:#x}, expected {OLD_CAVE:#x}/{NEW_CAVE:#x}")

    old_signatures, old_used = read_existing_signatures(native)
    require(old_signatures and all(signature.hex() in EXPECTED_BASE_SIGS
                                   for signature in old_signatures),
            "base libil2cpp hook prefixes do not match this build")
    combined, seen = list(old_signatures), {bytes(signature) for signature in old_signatures}
    for _table, signature in signatures:
        if signature in seen:
            continue
        combined.append(signature)
        seen.add(signature)
    count = len(combined)
    payload = build_payload(combined)
    end = NEW_CAVE + len(payload)
    helper = (end + 15) & ~15
    require(end <= ZERO_END, f"payload {len(payload)} B exceeds the zero cave")
    require(helper + 20 <= ZERO_END, f"helper does not fit: {helper:#x}")

    already = (hook_target == NEW_CAVE
               and native[NEW_CAVE:NEW_CAVE + len(payload)] == payload)
    if already:
        native[helper:helper + 20] = hide_marry_payload(helper)
    else:
        require(native[NEW_CAVE:helper] == bytes(helper - NEW_CAVE),
                "new cave is not zero; the APK was patched with a different table set")
        native[NEW_CAVE:end] = payload
        struct.pack_into("<I", native, HOOK, b_insn(HOOK, NEW_CAVE))
    percent = patch_date_percent(native)
    married = patch_hide_marry(native, helper)

    # 自检: 重解析 payload / sig / hook 目标 / 零区 / 辅助函数 / 调用点。
    def word(index: int) -> int:
        return struct.unpack_from("<I", native, NEW_CAVE + index * 4)[0]

    require(word(0) & 0xFF000000 == 0xB4000000, "new payload header mismatch")
    index, blocks = 6, 0
    while word(index + 8) == RET:
        require(word(index) & 0xFC000000 == 0x58000000, f"block {blocks} is not ldr literal")
        index += 9
        blocks += 1
    require(blocks == count, f"payload has {blocks} blocks, expected {count}")
    require(word(index) == ORIGINAL, f"payload fallback is {word(index):08x}")
    literals = NEW_CAVE + (index + 2) * 4
    recovered = [bytes(native[literals + item * 16:literals + (item + 1) * 16])
                 for item in range(count)]
    require(recovered == [bytes(signature) for signature in combined],
            "recovered prefixes do not match the table signatures")
    require(branch_target(struct.unpack_from("<I", native, HOOK)[0], HOOK) == NEW_CAVE,
            "HOOK does not point at the new cave")
    require(native[end:helper] == bytes(helper - end), "payload padding is not zero")
    require(native[helper + 20:ZERO_END] == bytes(ZERO_END - helper - 20),
            "zero cave tail was modified")
    helper_words = [struct.unpack_from("<I", native, helper + item * 4)[0] for item in range(5)]
    require(helper_words[0] == 0x7100001F | (CHUJIU << 10) | (1 << 5),
            "helper cmp w1,#1010 mismatch")
    require(helper_words[1] == 0x54000060 and helper_words[2] == 0x52800020
            and helper_words[3] == RET, "helper prologue mismatch")
    require(branch_target(helper_words[4], helper + 16) == CHECK_MARRIED,
            "helper tail-call does not reach CheckMarried")
    for site in MARRIED_SITES:
        require(branch_target(struct.unpack_from("<I", native, site)[0], site) == helper,
                f"site {site:#x} does not call the helper")

    audit = [
        f"libil2cpp: hook {HOOK:#x} -> {NEW_CAVE:#x}; 旧 payload {old_used} B "
        f"({len(old_signatures)} 前缀) -> {len(payload)} B ({count} 前缀); "
        f"辅助函数 {helper:#x}; 剩余零区 {ZERO_END - helper - 20} B",
        percent,
        *married,
    ]
    return bytes(native), audit


# ---------------------------------------------------------------- 主流程
def patch(apk: Path, assets: Path, output: Path,
          ratio: float = MARRY_SCENE_RATIO) -> dict[str, str]:
    require(apk.exists(), f"missing APK: {apk}")
    output.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    audit: dict[str, object] = {}

    tables, signatures, table_audit = patch_tables(apk, assets)
    for entry, payload in tables.items():
        target = output / (entry + ".bin")
        target.write_bytes(payload)
        manifest[DATA_PREFIX + entry] = str(target.resolve())
    for record in table_audit:
        audit[DATA_PREFIX + TABLE_ENTRIES[record["table"]]] = record
        print(f"{record['table']:<26} {TABLE_ENTRIES[record['table']][:12]} "
              f"明文 {record['plain_bytes'][0]} -> {record['plain_bytes'][1]} B  "
              f"{record['detail']}")

    art, art_audit = patch_art(assets, output, ratio)
    for entry, payload in art.items():
        target = output / (entry + ".bin")
        target.write_bytes(payload)
        manifest[DATA_PREFIX + entry] = str(target.resolve())
    global_payload, global_audit = patch_global(apk, art)
    (output / (GG + ".bin")).write_bytes(global_payload)
    manifest[DATA_PREFIX + GG] = str((output / (GG + ".bin")).resolve())
    audit[DATA_PREFIX + GG] = {"detail": global_audit}
    for line in art_audit:
        print(line)
    for line in global_audit:
        print(line)

    native_payload, native_audit = patch_native(apk, signatures)
    (output / "libil2cpp.so.bin").write_bytes(native_payload)
    manifest[NATIVE] = str((output / "libil2cpp.so.bin").resolve())
    audit[NATIVE] = {"detail": native_audit}
    for line in native_audit:
        print(line)

    (output / "patches.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (output / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print(f"patched {len(manifest)} entries; reseal/sign is a separate step")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS)
    parser.add_argument("--marry-scene-ratio", type=float, default=MARRY_SCENE_RATIO)
    arguments = parser.parse_args()
    patch(arguments.apk, arguments.assets, arguments.output, arguments.marry_scene_ratio)
