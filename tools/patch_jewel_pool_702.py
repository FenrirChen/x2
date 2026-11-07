"""Build the client-side assets for jewel pool 22702 (莫格尔祖母绿 / 6★ 宝石姬).

The official tables already carry the pool 22702 rows and JewelBase 1251004, but
the shipped client never referenced them: the illustration / pool cover / tab
art are absent and the three pool tables never mention the new jewel.  As a
result the pool paints as a white card and top draws cannot award 1251004.

This build-time tool injects the three art resources and repairs the three
tables, without touching the reference APK.  Seven zip entries are rewritten:

  A. 11f10428 (BaoShiJi_3 carrier): + Texture2D pid=1000 (688x828 RGBA32)
     + Sprite pid=1001 `BaoShiJi_2` (whole image).  The original pid 1/2 are
     left untouched.
  B. 2f27eb21 (Cover709 carrier): + Texture2D pid=1000 (1404x592 RGBA32)
     + Sprite pid=1001 `GuangGaoTu_Cover702`.
  C. 83629c10 (Draw atlas): + Texture2D pid=1000 (220x68 RGBA32)
     + Sprite pid=1001 `ChouJiang_Tab702`; the existing 59 sprites stay as-is.
  D. globalgamemanagers `ResourceManager.m_Container`: add
     `uialtas/drawing/jewel/baoshiji_2` and
     `uialtas/draw/guanggaotu_cover702` (two entries each), and append the two
     Draw sprites to the existing `uialtas/altas/draw` group (60 -> 62).
     ★ Keys are lowercase and strictly sorted; the runtime lowercases the
       request and binary-searches, so an uppercase or misplaced key hides the
       resource and corrupts lookups for its neighbours.
  E. DrawParam 22702: insert f35 = 1251004 after f33 (preview jewel).  f36
     (preview position) is intentionally left empty: the 22700/22701 values do
     not scale like JewelBase.PaintingPosition and are not understood yet.
  F. DrawRules 22702: insert f3 = 1251004 after f2 (UP jewel) and put 1251004
     at the head of the f5 pool list.
  G. Gift 750108 (top): prepend weight 496 / item 1251004; Gift 750106
     (common): insert weight 52 / item 1251004 before the 1251014 anchor.
     Both sides match src/x2server/data/wish_catalog.json exactly.

Weights copy the ratios of the sibling single-UP jewel pool 22701: top 496 of
992 = 50% (22701 is 51.6%); common 52 of 10074 = 0.516% (22701 is 0.52%).

The three tables are Unity TextAssets: the first 128 B is an RSA block and the
rest is position-XOR encrypted.  Edits change the plaintext length, so the RSA
header is preserved, only the encrypted tail is rebuilt, and UnityPy re-serialises
the entry.  Art injection appends objects to existing SerializedFiles.

    python tools/patch_jewel_pool_702.py --apk <reference.apk> --output <dir>

The output directory holds files named after their zip entry plus `.bin`,
`patches.json`, and `audit.json`.  Replace the entries, then re-sign with the
local development key; this tool never signs or installs anything.

The art is project-made compatibility material: the official client has no
BaoShiJi_2 illustration, Cover702 banner or Tab702 tab.  The illustration is
shared by JewelBase 1251004/1251005/1251006; the banner/tab are composed for
pool 22702.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS / "analysis"))
from _client_table_wire import (  # noqa: E402
    convert_data_bytes,
    parse_message,
    parse_table_container,
    read_varint,
    rsa_public_unpad,
)

DATA_PREFIX = "assets/bin/Data/"
DEFAULT_ART_DIR = TOOLS / "assets" / "jewel_pool_702"

POOL = 22702
NEW_ITEM = 1251004
TOP_WEIGHT = 496
COMMON_WEIGHT = 52

GLOBAL = "globalgamemanagers"
DRAW_PARAM = "794cf065a19ef3543aa8ec8dda10e252"
DRAW_RULES = "109c23e5b633a7943b46f54df86ab23e"
GIFT = "97f907f95af754641b60175964616b99"
TABLES = ((DRAW_PARAM, "DrawParam"), (DRAW_RULES, "DrawRules"), (GIFT, "Gift"))

TEXTURE_CLASS, SPRITE_CLASS, RESOURCE_CLASS, TEXT_CLASS = 28, 213, 147, 49
NEW_TEXTURE_PID, NEW_SPRITE_PID = 1000, 1001
NEW_RENDER_TAIL = 21300000
QUAD_INDEX_BUFFER = [0, 0, 1, 0, 2, 0, 2, 0, 1, 0, 3, 0]


class PatchError(RuntimeError):
    """The input APK does not match the reference layout, or cannot be patched safely."""


@dataclass(frozen=True)
class Piece:
    label: str
    container_key: str
    entry: str
    sprite_name: str
    file_name: str
    size: tuple[int, int]
    # The pre-existing entry used to copy the container's m_FileID.  For the
    # Draw atlas this is the same key, because the group already exists.
    file_id_source: str


PIECES = (
    Piece("立绘", "uialtas/drawing/jewel/baoshiji_2",
          "11f10428ab85c83458e81c7c4acc3909", "BaoShiJi_2",
          "baoshiji_2_688x828.png", (688, 828),
          "uialtas/drawing/jewel/baoshiji_3"),
    Piece("横幅", "uialtas/draw/guanggaotu_cover702",
          "2f27eb218a7d46144b76f8574a7912ca", "GuangGaoTu_Cover702",
          "cover702_1404x592.png", (1404, 592),
          "uialtas/draw/guanggaotu_cover709"),
    Piece("页签", "uialtas/altas/draw",
          "83629c106e3c12644a26a22b89a7f24d", "ChouJiang_Tab702",
          "tab702_220x68.png", (220, 68),
          "uialtas/altas/draw"),
)


# ---------------------------------------------------------------- 基础工具
def _varint(value: int) -> bytes:
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def _field(number: int, value: int) -> bytes:
    return _varint(number << 3) + _varint(value)


def _xor_table(blob: bytes) -> bytes:
    """Re-apply the position XOR (the involution half of convert_data_bytes)."""
    out = bytearray(blob)
    index, delta = 1, 0
    while index < len(out):
        out[index] ^= (delta + index) & 255
        index <<= 1
        delta -= 1
    index, delta = len(out) - 1, 0
    while index > 0:
        out[index] ^= (delta + index) & 255
        index >>= 1
        delta -= 1
    return bytes(out)


def quad_mesh(width: float, height: float) -> bytes:
    """Four vertices / 20 B each (position float32x3 + UV float32x2)."""
    half_w, half_h = width / 200.0, height / 200.0
    vertices = (
        ((-half_w, half_h), (0.0, 1.0)),
        ((half_w, half_h), (1.0, 1.0)),
        ((-half_w, -half_h), (0.0, 0.0)),
        ((half_w, -half_h), (1.0, 0.0)),
    )
    out = bytearray()
    for (x, y), (u, v) in vertices:
        out += struct.pack("<fff", x, y, 0.0) + struct.pack("<ff", u, v)
    return bytes(out)


def hashed_render_key(container_key: str) -> list[int]:
    digest = hashlib.md5(container_key.encode("utf-8")).digest()  # noqa: S324 - asset key
    return [int.from_bytes(digest[i * 4:i * 4 + 4], "little") for i in range(4)]


# ---------------------------------------------------------------- SerializedFile
def read_entry(apk: Path, entry: str) -> bytes:
    with zipfile.ZipFile(apk) as archive:
        try:
            return archive.read(DATA_PREFIX + entry)
        except KeyError as exc:
            raise PatchError(f"{apk} is missing {DATA_PREFIX}{entry}") from exc


def load_serialized(blob: bytes):
    import UnityPy

    environment = UnityPy.load(blob)
    return next(iter(environment.files.values()))


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
    """Append an object by copying the type descriptor of an existing class."""
    from UnityPy.enums import ClassIDType
    from UnityPy.files import ObjectReader

    for _type_id, serialized_type in enumerate(serialized.types):
        if serialized_type.class_id == class_id:
            break
    else:
        raise PatchError(f"serialized file has no class {class_id} template")
    raw = serialise_tree(serialized, class_id, tree)
    serialized.objects[path_id] = ObjectReader(
        serialized, None, path_id, _type_id, serialized_type, class_id,
        ClassIDType(class_id), 0, len(raw), None, None, data=raw)


def texture_tree(template: dict, image, name: str) -> dict:
    """Copy an existing Texture2D, changing only name / size / format / pixels."""
    from PIL import Image
    from UnityPy.enums import TextureFormat

    try:
        flip = Image.Transpose.FLIP_TOP_BOTTOM
    except AttributeError:  # Pillow < 9.1
        flip = Image.FLIP_TOP_BOTTOM
    raw = image.convert("RGBA").transpose(flip).tobytes()
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
    tree["m_LightmapFormat"] = 6
    tree["m_ColorSpace"] = 1
    tree["m_StreamData"] = {"offset": 0, "size": 0, "path": ""}
    tree["image data"] = raw
    return tree


def sprite_tree(template: dict, texture_pid: int, width: int, height: int,
                name: str, container_key: str) -> dict:
    """Copy an existing Sprite and replace its mesh with a self-consistent quad."""
    tree = copy.deepcopy(template)
    half_w, half_h = width / 200.0, height / 200.0
    tree["m_Name"] = name
    tree["m_Rect"] = {"x": 0.0, "y": 0.0, "width": float(width), "height": float(height)}
    tree["m_Offset"] = {"x": 0.0, "y": 0.0}
    tree["m_Border"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0}
    tree["m_Pivot"] = {"x": 0.5, "y": 0.5}
    tree["m_Extrude"] = 1
    tree["m_IsPolygon"] = False
    tree["m_RenderDataKey"] = [
        dict(zip(("data[0]", "data[1]", "data[2]", "data[3]"),
                 hashed_render_key(container_key), strict=True)),
        NEW_RENDER_TAIL,
    ]
    tree["m_AtlasTags"] = []
    tree["m_SpriteAtlas"] = {"m_FileID": 0, "m_PathID": 0}
    render_data = tree["m_RD"]
    render_data["texture"] = {"m_FileID": 0, "m_PathID": texture_pid}
    render_data["alphaTexture"] = {"m_FileID": 0, "m_PathID": 0}
    render_data["m_VertexData"]["m_DataSize"] = quad_mesh(width, height)
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
                            "m_Extent": {"x": half_w, "y": half_h, "z": 0.0}}
    render_data["textureRect"] = {"x": 0.0, "y": 0.0,
                                  "width": float(width), "height": float(height)}
    render_data["textureRectOffset"] = {"x": 0.0, "y": 0.0}
    render_data["atlasRectOffset"] = {"x": -1.0, "y": -1.0}
    render_data["settingsRaw"] = 64
    render_data["uvTransform"] = {"x": 100.0, "y": width / 2.0,
                                  "z": 100.0, "w": height / 2.0}
    render_data["downscaleMultiplier"] = 1.0
    tree["m_PhysicsShape"] = [[{"x": -half_w, "y": -half_h}, {"x": half_w, "y": -half_h},
                               {"x": half_w, "y": half_h}, {"x": -half_w, "y": half_h}]]
    return tree


# ---------------------------------------------------------------- 容器
def insert_container_group(container: list, key: str, file_id: int,
                           path_ids: tuple[int, int]) -> tuple[int, str]:
    """Insert a sorted lowercase group; existing groups grow at their block end."""
    keys = [name for name, _ in container]
    if key in keys:
        position = max(i for i, name in enumerate(keys) if name == key) + 1
        if position < len(container) and not keys[position] > key:
            raise PatchError(f"container {key!r} block is not followed by a greater key")
        placement = "existing"
    else:
        position = next((i for i, name in enumerate(keys) if name > key), len(container))
        placement = "new"
    container[position:position] = [
        (key, {"m_FileID": file_id, "m_PathID": path_id}) for path_id in path_ids
    ]
    return position, placement


def patch_container(apk: Path) -> tuple[bytes, dict]:
    serialized = load_serialized(read_entry(apk, GLOBAL))
    manager = next((o for o in objects(serialized) if o.class_id == RESOURCE_CLASS), None)
    if manager is None:
        raise PatchError("globalgamemanagers holds no ResourceManager")
    tree = manager.read_typetree()
    container = list(tree["m_Container"])
    keys = [name for name, _ in container]
    if any(name.isupper() for name in keys):
        raise PatchError("container keys are not all lowercase")
    if keys != sorted(keys):
        raise PatchError("container is not sorted")
    before = len(container)

    inserted = []
    for piece in PIECES:
        values = [value for name, value in container if name == piece.file_id_source]
        if not values:
            raise PatchError(f"container has no {piece.file_id_source!r} entry")
        # Supplemental atlas groups legitimately span multiple files. Resolve
        # the original carrier by its external path, not by the whole group.
        file_ids = {value["m_FileID"] for value in values
                    if value["m_FileID"] > 0 and
                    serialized.externals[value["m_FileID"] - 1].path == piece.entry}
        if len(file_ids) != 1:
            raise PatchError(f"{piece.file_id_source!r} entries disagree on m_FileID")
        file_id = file_ids.pop()
        external = serialized.externals[file_id - 1]
        resolved = getattr(external, "path", None) or getattr(external, "name", None)
        if resolved != piece.entry:
            raise PatchError(f"externals[{file_id - 1}] is {resolved!r}, "
                             f"expected {piece.entry!r}")
        if piece.container_key == "uialtas/drawing/jewel/baoshiji_2":
            container = [(key, value) for key, value in container if not (
                key == piece.container_key and value["m_FileID"] > 0 and
                serialized.externals[value["m_FileID"] - 1].path == "x2_mogul_drawing.assets")]
        position, placement = insert_container_group(
            container, piece.container_key, file_id, (NEW_TEXTURE_PID, NEW_SPRITE_PID))
        inserted.append({"key": piece.container_key, "index": position,
                         "placement": placement, "file_id": file_id,
                         "path_ids": [NEW_TEXTURE_PID, NEW_SPRITE_PID]})

    after_keys = [name for name, _ in container]
    if after_keys != sorted(after_keys):
        raise PatchError("container lost its ordering")
    tree["m_Container"] = container
    manager.save_typetree(tree)
    payload = serialized.save()

    check = load_serialized(payload)
    checked = next(o for o in objects(check) if o.class_id == RESOURCE_CLASS)
    after = checked.read_typetree()["m_Container"]
    after_keys = [name for name, _ in after]
    if len(after) != len(container) or after_keys != sorted(after_keys):
        raise PatchError("patched container is malformed")
    if any(name.isupper() for name in after_keys):
        raise PatchError("patched container has uppercase keys")
    for piece in PIECES:
        got = [value["m_PathID"] for name, value in after if name == piece.container_key]
        if got[-2:] != [NEW_TEXTURE_PID, NEW_SPRITE_PID]:
            raise PatchError(f"container {piece.container_key!r} -> {got[-2:]}")
    return payload, {"entries_before": before, "entries_after": len(after),
                     "inserted": inserted}


# ---------------------------------------------------------------- 载体
def patch_carrier(apk: Path, piece: Piece, image) -> tuple[bytes, dict]:
    serialized = load_serialized(read_entry(apk, piece.entry))
    existing = objects(serialized)
    used = {o.path_id for o in existing}
    if used & {NEW_TEXTURE_PID, NEW_SPRITE_PID}:
        raise PatchError(f"{piece.entry} already uses the reserved path ids")
    texture_template = next((o.read_typetree() for o in existing
                             if o.class_id == TEXTURE_CLASS), None)
    sprite_template = next((o.read_typetree() for o in existing
                            if o.class_id == SPRITE_CLASS), None)
    if texture_template is None or sprite_template is None:
        raise PatchError(f"{piece.entry} lacks a Texture2D/Sprite template")

    width, height = image.size
    add_object(serialized, NEW_TEXTURE_PID, TEXTURE_CLASS,
               texture_tree(texture_template, image, piece.sprite_name))
    add_object(serialized, NEW_SPRITE_PID, SPRITE_CLASS,
               sprite_tree(sprite_template, NEW_TEXTURE_PID, width, height,
                           piece.sprite_name, piece.container_key))
    payload = serialized.save()

    # 自检: 回读像素 / Sprite 绑定 / 四边形网格 / 既有对象。
    check = load_serialized(payload)
    textures = {o.path_id: o for o in objects(check) if o.class_id == TEXTURE_CLASS}
    sprites = {o.path_id: o for o in objects(check) if o.class_id == SPRITE_CLASS}
    if NEW_TEXTURE_PID not in textures or NEW_SPRITE_PID not in sprites:
        raise PatchError(f"{piece.entry} lost the new objects")
    if not used <= set(textures) | set(sprites) or len(sprites) < len(
            [o for o in existing if o.class_id == SPRITE_CLASS]) + 1:
        raise PatchError(f"{piece.entry} lost its original objects")
    back = textures[NEW_TEXTURE_PID].parse_as_object().image
    if back.size != image.size or back.convert("RGBA").tobytes() != image.convert(
            "RGBA").tobytes():
        raise PatchError(f"{piece.entry} texture is not pixel identical")
    tree = sprites[NEW_SPRITE_PID].read_typetree()
    render_data = tree["m_RD"]
    submesh = render_data["m_SubMeshes"][0]
    if tree["m_Name"] != piece.sprite_name:
        raise PatchError(f"{piece.entry} sprite name is {tree['m_Name']!r}")
    if render_data["texture"] != {"m_FileID": 0, "m_PathID": NEW_TEXTURE_PID}:
        raise PatchError(f"{piece.entry} sprite is not bound to the new texture")
    if submesh["indexCount"] != 6 or submesh["vertexCount"] != 4:
        raise PatchError(f"{piece.entry} quad mesh is inconsistent")
    if len(render_data["m_IndexBuffer"]) != 12 or len(
            render_data["m_VertexData"]["m_DataSize"]) != 80:
        raise PatchError(f"{piece.entry} quad buffers have the wrong size")
    return payload, {"label": piece.label, "texture": NEW_TEXTURE_PID,
                     "sprite": NEW_SPRITE_PID, "name": piece.sprite_name,
                     "image": [width, height], "source": piece.file_name}


# ---------------------------------------------------------------- 表
def split_array(plain: bytes):
    """Split the (4B count + all keys + all rows) framing used by these tables."""
    count = int.from_bytes(plain[:4], "little")
    position = 4
    keys: list[int] = []
    while position < len(plain):
        marker = position
        tag, position = read_varint(plain, position)
        if tag & 7 or tag >> 3 != 1:
            position = marker
            break
        key, position = read_varint(plain, position)
        keys.append(key)
    keys_end = position
    rows: list[bytes] = []
    spans: list[int] = []
    while position < len(plain):
        tag, position = read_varint(plain, position)
        if tag != (2 << 3 | 2):
            raise PatchError("table row is not length delimited")
        length, position = read_varint(plain, position)
        spans.append(position)
        rows.append(plain[position:position + length])
        position += length
    if not (len(keys) == len(rows) == count):
        raise PatchError("table framing is not a key/row array")
    return count, keys, rows, spans, keys_end


def build_array(plain: bytes, keys_end: int, rows: list[bytes]) -> bytes:
    out = bytearray(plain[:keys_end])
    for row in rows:
        out += b"\x12" + _varint(len(row)) + row
    return bytes(out)


def _fields(row: bytes):
    return parse_message(row)[0]


def _insert(row: bytes, position: int, chunk: bytes) -> bytes:
    return row[:position] + chunk + row[position:]


def edit_draw_param_row(row: bytes) -> tuple[bytes, str]:
    fields = _fields(row)
    if any(field.field == 35 for field in fields):
        raise PatchError("DrawParam 22702 already has f35")
    if any(field.field == 36 for field in fields):
        raise PatchError("DrawParam 22702 already has f36")
    anchors = [field for field in fields if field.field == 33]
    if len(anchors) != 1:
        raise PatchError("DrawParam 22702 has no unique f33 anchor")
    position = anchors[0].end
    patched = _insert(row, position, _field(35, NEW_ITEM))
    after = _fields(patched)
    if [field.value for field in after if field.field == 35] != [NEW_ITEM]:
        raise PatchError("DrawParam f35 was not written")
    return patched, f"f35 += {NEW_ITEM} (after f33; f36 left empty)"


def edit_draw_rules_row(row: bytes) -> tuple[bytes, str]:
    fields = _fields(row)
    if any(field.field == 3 for field in fields):
        raise PatchError("DrawRules 22702 already has f3")
    f2 = [field for field in fields if field.field == 2]
    f5 = [field for field in fields if field.field == 5]
    if len(f2) != 1 or not f5:
        raise PatchError("DrawRules 22702 lacks the f2/f5 anchors")
    up_position = f2[0].end
    pool_position = f5[0].start
    # Apply the later insertion first so the earlier offset stays valid.  When
    # f2 and the first f5 touch, both land on the same offset: write f5 first
    # so that f3 ends up immediately after f2.
    insertions = [
        (up_position, 0, _field(3, NEW_ITEM)),
        (pool_position, 1, _field(5, NEW_ITEM)),
    ]
    patched = row
    for position, _, chunk in sorted(insertions, key=lambda item: item[:2], reverse=True):
        patched = _insert(patched, position, chunk)
    after = _fields(patched)
    if [field.field for field in after][:3] != [1, 2, 3]:
        raise PatchError("DrawRules f3 was not written after f2")
    if [field.value for field in after if field.field == 3] != [NEW_ITEM]:
        raise PatchError("DrawRules f3 was not written")
    if [field.value for field in after if field.field == 5][:1] != [NEW_ITEM]:
        raise PatchError("DrawRules f5 head was not written")
    return patched, f"f3 += {NEW_ITEM}; f5 head += {NEW_ITEM}"


def edit_gift_row(row: bytes, key: int) -> tuple[bytes, str]:
    fields = _fields(row)
    numbers = [field.field for field in fields]
    if numbers[:2] != [1, 2]:
        raise PatchError(f"Gift {key} does not start with f1/f2")
    weights = [field for field in fields if field.field == 3]
    items = [field for field in fields if field.field == 4]
    if len(weights) != len(items) or not weights:
        raise PatchError(f"Gift {key} weights/items are not paired")
    if weights[-1].start > items[0].start:
        raise PatchError(f"Gift {key} interleaves weights and items")
    if NEW_ITEM in [field.value for field in items]:
        raise PatchError(f"Gift {key} already lists {NEW_ITEM}")

    if key == 750108:
        weight_position, item_position = weights[0].start, items[0].start
        weight_audit = TOP_WEIGHT
        placement = "head"
    else:
        anchors = [field for field in items if field.value == 1251014]
        if len(anchors) != 1:
            raise PatchError(f"Gift {key} has no unique 1251014 anchor")
        index = items.index(anchors[0])
        weight_position = weights[index].start
        item_position = anchors[0].start
        weight_audit = COMMON_WEIGHT
        placement = f"before 1251014 (index {index})"

    patched = row
    for position in sorted((weight_position, item_position), reverse=True):
        chunk = (_field(3, weight_audit) if position == weight_position
                 else _field(4, NEW_ITEM))
        patched = _insert(patched, position, chunk)
    after_weights = [field.value for field in _fields(patched) if field.field == 3]
    after_items = [field.value for field in _fields(patched) if field.field == 4]
    if len(after_weights) != len(after_items):
        raise PatchError(f"Gift {key} weights/items fell out of alignment")
    index = after_items.index(NEW_ITEM)
    if after_weights[index] != weight_audit:
        raise PatchError(f"Gift {key} gave {NEW_ITEM} weight {after_weights[index]}")
    return patched, f"{weight_audit}/{NEW_ITEM} at {placement}"


def reencrypt(encrypted: bytes, plain: bytes, prefix: bytes) -> bytes:
    obfuscated = _xor_table(plain)
    if obfuscated[:len(prefix)] != prefix:
        raise PatchError("the RSA-covered prefix would change")
    patched = encrypted[:128] + obfuscated[len(prefix):]
    if convert_data_bytes(patched) != plain:
        raise PatchError("re-encryption round trip failed")
    return patched


def _patch_one_row(encrypted: bytes, key: int, editor,
                   table_name: str) -> tuple[bytes, str, list[int]]:
    table = parse_table_container(encrypted)
    if table["kind"] != "array":
        raise PatchError(f"{table_name} is not a key/row array")
    plain, prefix = table["plain"], rsa_public_unpad(encrypted[:128])
    count, keys, rows, spans, keys_end = split_array(plain)
    index = keys.index(key)
    if spans[index] < len(prefix):
        raise PatchError(f"{table_name} {key} sits inside the RSA-covered prefix")
    patched_row, description = editor(rows[index])
    new_rows = list(rows)
    new_rows[index] = patched_row
    patched = reencrypt(encrypted, build_array(plain, keys_end, new_rows), prefix)

    decoded = parse_table_container(patched)
    if decoded["kind"] != "array" or decoded["keys"] != keys:
        raise PatchError(f"{table_name} keys changed")
    changed = [name for name, before, after in zip(keys, rows, decoded["items"], strict=True)
               if before != after]
    if changed != [key]:
        raise PatchError(f"{table_name} changed unexpected rows: {changed}")
    return patched, description, changed


def patch_draw_param(encrypted: bytes) -> tuple[bytes, str]:
    patched, description, _ = _patch_one_row(
        encrypted, POOL, edit_draw_param_row, "DrawParam")
    return patched, description


def patch_draw_rules(encrypted: bytes) -> tuple[bytes, str]:
    patched, description, _ = _patch_one_row(
        encrypted, POOL, edit_draw_rules_row, "DrawRules")
    return patched, description


def patch_gift(encrypted: bytes) -> tuple[bytes, str]:
    table = parse_table_container(encrypted)
    if table["kind"] != "array":
        raise PatchError("Gift is not a key/row array")
    plain, prefix = table["plain"], rsa_public_unpad(encrypted[:128])
    count, keys, rows, spans, keys_end = split_array(plain)
    new_rows = list(rows)
    descriptions = []
    targets = (750108, 750106)
    for key in targets:
        index = keys.index(key)
        if spans[index] < len(prefix):
            raise PatchError(f"Gift {key} sits inside the RSA-covered prefix")
        new_rows[index], description = edit_gift_row(rows[index], key)
        descriptions.append(description)
    patched = reencrypt(encrypted, build_array(plain, keys_end, new_rows), prefix)
    decoded = parse_table_container(patched)
    if decoded["kind"] != "array" or decoded["keys"] != keys:
        raise PatchError("Gift keys changed")
    changed = [name for name, before, after in zip(keys, rows, decoded["items"], strict=True)
               if before != after]
    if changed != sorted(targets):
        raise PatchError(f"Gift changed unexpected rows: {changed}")
    return patched, "; ".join(descriptions)


def split_raw_text_asset(raw: bytes, table: str) -> tuple[bytes, bytes]:
    """TextAsset raw bytes -> (name header, m_Script).

    Never use read_typetree here: UnityPy decodes m_Script as UTF-8 and would
    destroy the encrypted binary payload on the way back.
    """
    length = int.from_bytes(raw[:4], "little")
    if raw[4:4 + length].decode("utf-8") != table:
        raise PatchError(f"expected a {table} TextAsset")
    position = (4 + length + 3) // 4 * 4
    script_size = int.from_bytes(raw[position:position + 4], "little")
    if position + 4 + script_size > len(raw):
        raise PatchError("m_Script runs past the object")
    return raw[:position], raw[position + 4:position + 4 + script_size]


def rebuild_table(apk: Path, entry: str, table: str, repair) -> tuple[bytes, dict]:
    serialized = load_serialized(read_entry(apk, entry))
    existing = objects(serialized)
    if len(existing) != 1 or existing[0].class_id != TEXT_CLASS:
        raise PatchError(f"{entry} is not a single TextAsset")
    head, encrypted = split_raw_text_asset(existing[0].get_raw_data(), table)
    patched, description = repair(encrypted)
    body = head + len(patched).to_bytes(4, "little") + patched
    existing[0].set_raw_data(body + b"\x00" * (-len(body) % 4))
    payload = serialized.save()

    check = load_serialized(payload)
    checked = objects(check)
    if len(checked) != 1 or checked[0].class_id != TEXT_CLASS:
        raise PatchError(f"{entry} lost its TextAsset")
    _, again = split_raw_text_asset(checked[0].get_raw_data(), table)
    if convert_data_bytes(again) != convert_data_bytes(patched):
        raise PatchError(f"{entry} payload does not round trip")
    return payload, {"table": table, "edit": description,
                     "encrypted_bytes": [len(encrypted), len(again)]}


# ---------------------------------------------------------------- 主流程
def read_png_size(path: Path) -> tuple[int, int]:
    """Read the IHDR dimensions without depending on Pillow."""
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise PatchError(f"{path} is not a PNG")
    return int.from_bytes(header[16:20], "big"), int.from_bytes(header[20:24], "big")


def patch(apk: Path, art_dir: Path, output: Path) -> dict[str, str]:
    from PIL import Image

    output.mkdir(parents=True, exist_ok=True)
    images = {}
    for piece in PIECES:
        path = art_dir / piece.file_name
        size = read_png_size(path)
        if size != piece.size:
            raise PatchError(f"{path} is {size}, expected {piece.size}")
        images[piece] = Image.open(path).convert("RGBA")

    steps = [(piece.entry, lambda piece=piece: patch_carrier(apk, piece, images[piece]))
             for piece in PIECES]
    steps += [(GLOBAL, lambda: patch_container(apk))]
    steps += [(DRAW_PARAM, lambda: rebuild_table(apk, DRAW_PARAM, "DrawParam",
                                                 patch_draw_param)),
              (DRAW_RULES, lambda: rebuild_table(apk, DRAW_RULES, "DrawRules",
                                                 patch_draw_rules)),
              (GIFT, lambda: rebuild_table(apk, GIFT, "Gift", patch_gift))]

    manifest: dict[str, str] = {}
    audit: dict[str, dict] = {}
    for entry, build in steps:
        payload, record = build()
        target = output / (entry + ".bin")
        target.write_bytes(payload)
        record["bytes"] = len(payload)
        record["sha256"] = hashlib.sha256(payload).hexdigest()
        manifest[DATA_PREFIX + entry] = str(target.resolve())
        audit[DATA_PREFIX + entry] = record
        print(f"{entry:<46} {len(payload):>10} B  {record['sha256'][:16]}")

    (output / "patches.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"patched {len(manifest)} assets; RSA prefixes and untouched rows are preserved")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--art-dir", type=Path, default=DEFAULT_ART_DIR)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    patch(arguments.apk, arguments.art_dir, arguments.output)
