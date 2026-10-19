"""Restore the shelved 静影糜株 appearance (Appearance/Shop 1223003) client assets.

Build-time only. 静影糜株 is 伊邪纳岐 (hero 1030) 的 5 星觉醒外观; 官方的
Appearance 1223003 行仍在权威表里, 但配套资源被当作废案剔除, 所以商品货位
1980045 一上架就是空白卡片 / 空白详情页 / 无法解锁头像。服务端加回 1980045
(见 src/x2server/data/appearance_shop_catalog.json) 之后, 还需要把下列资源
按原版命名补进客户端:

  Appearance 1223003 引用     原名容器键                          本工具注入
  --------------------------  ----------------------------------  --------------------
  Icon                        SkinHead01/Hero_Icon_103003         pid 101(150x150)
  HalfDrawing                 UIAltas/HeroIcon_H/Hero_Icon_.._H   pid 1002(264x600)
  ShowImg                     UIAltas/SkinDrawing/SkinDrawing_.. pid 1001(1980x2048)

五处改动, 全部只读写原版资源, 不覆盖参考包:

  A. 载体 9c7fdb35 (与 1222703 立绘同文件): 追加 Texture2D pid=1000 (原画整图
     RGBA32) + Sprite pid=1001 `SkinDrawing_1223003` (整图) + Sprite pid=1002
     `Hero_Icon_103003_H` (与 1001 共用同一张贴图, 只取 264x600 卡片框, 不额外
     占体积)。既有 pid 1/2 原样保留。
  B. 图集 2af4a6e8 (skinhead01, 34 张头像): 追加 Texture2D pid=100 (150x150
     RGBA32) + Sprite pid=101 `Hero_Icon_103003`。原图集贴图是 TextureFormat=47
     (压缩系), 为避免重编码压缩纹理, 新头像另起一张 RGBA32 贴图; 原贴图与 34 张
     Sprite 一律不动。
  C. globalgamemanagers 的 ResourceManager.m_Container: 新增
     `uialtas/skindrawing/skindrawing_1223003` 与 `uialtas/heroicon_h/hero_icon_103003_h`
     (各 2 条, 指向 A 的 pid 1000+1001 / 1000+1002), 并在
     `uialtas/altas/skinhead01` 组末尾补 1 条指向 B 的 pid 101。
     ★ 容器键全小写且严格有序; 运行时把请求串转小写后做区分大小写的二分查找,
       大写键或错位插入都会查不到并连带破坏邻近资源的查找。
  D. Appearance 表 (2c6eecbf) 1223003 行: 字段 15 SpineShow 清空
     (`SpineModle/SP_103003` -> 空)。客户端里 spinemodle/sp_103003 只是没有 atlas
     的残件, 详情页走 spine 分支会空引用并把初始化截断(顶栏返回按钮绑不上);
     清空后回落到 RawImage 分支, 详情页读 ShowImg = 我们注入的立绘。
  E. Appearance 表同行 字段 29 MainPaintingScale 110 -> 55: 主城立绘按
     (rect 像素 x scale/100) 铺满, 该皮肤原画 1980x2048 比常规皮肤大约 21%,
     用 55 抵消。另 UnitBase 表 (5c993e69) 1030 行 字段 48 AppearanceList
     追加 1223003, 否则神格详情的外观列表只有原皮 + 5 星觉醒两项。

两张表都是 Unity TextAsset: 前 128 B 是 RSA 头, 其余是位置异或后的明文。
D 会缩短明文, E 会加长明文, 两者都不能等长原地替换, 所以保留 RSA 头、只重加密
密文尾部, 再用 UnityPy 重建该 SerializedFile 条目(这两个文件都只有 1 个
TextAsset 对象、无 externals)。A/B/C 都是往既有 SerializedFile 追加对象, 同样
整文件重建。

    python tools/patch_izanagi_skin.py --apk <reference.apk> --output <dir>
    python tools/patch_izanagi_skin.py --apk <apk> --skin <原画.png> --output <dir>

输出目录里是可直接替换同名 zip 条目的资产, 外加 `patches.json`(条目 -> 产物路径)
和 `audit.json`(每处改动明细)。替换后必须用本地开发密钥重新签名才能安装;
工具自己不做签名, 也不安装到设备。源图与两张对照预览图见 `tools/assets/`。

原作者是否等同官方静影糜株原画未确认: 该 PNG 来自外部立绘合集, 只能确证
1223003 的官方名称与编号, 不能确证图像出处。行为与命名对齐官方表, 图像来源
标记为兼容素材。
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
    convert_data_bytes,
    parse_message,
    parse_table_container,
    read_varint,
    rsa_public_unpad,
)

DATA_PREFIX = "assets/bin/Data/"
DEFAULT_SKIN = TOOLS / "assets" / "izanagi_skin_1223003.png"

# 既有资源所在的文件(资源名与相邻皮肤 1222703 / 100303 同源)。
CARRIER = "9c7fdb35ebf462c42a28c35799e1d9da"
ATLAS = "2af4a6e8414c516489bc96b264245878"
GLOBAL = "globalgamemanagers"
APPEARANCE_TABLE = "2c6eecbf62e755847898fdb41e07d857"
UNIT_BASE_TABLE = "5c993e6912a40e541be49a4f5ed7abd7"

DRAWING_KEY = "uialtas/skindrawing/skindrawing_1223003"
HALF_ICON_KEY = "uialtas/heroicon_h/hero_icon_103003_h"
ATLAS_GROUP = "uialtas/altas/skinhead01"
DRAWING_SOURCE_KEY = "uialtas/skindrawing/skindrawing_1222703"

APPEARANCE_ID = 1223003
UNIT_ID = 1030
DRAWING = "SkinDrawing_1223003"
HALF_ICON = "Hero_Icon_103003_H"
HEAD_ICON = "Hero_Icon_103003"
SPINE_SHOW = b"SpineModle/SP_103003"
MAIN_PAINTING_SCALE_OLD = 110
MAIN_PAINTING_SCALE_NEW = 55
UNIT_APPEARANCE_LIST_OLD = [1223001, 1223002]

# 1980x2048 原画上的裁剪框(左上原点): 商店/神格竖版卡片 460x1045, 头像是 340x340 方框。
# 卡片框取整幅坐姿的取景, 与姊妹皮肤的竖版卡片一致; 早期的 264x600 只有头肩, 太近。
CARD_BOX = (700, 675, 1160, 1720)
HEAD_BOX = (860, 720, 1200, 1060)
HEAD_ICON_SIZE = 150

TEXTURE_CLASS, SPRITE_CLASS, RESOURCE_CLASS, TEXT_CLASS = 28, 213, 147, 49
CARRIER_TEXTURE_PID, CARRIER_DRAWING_PID, CARRIER_HALF_ICON_PID = 1000, 1001, 1002
ATLAS_TEXTURE_PID, ATLAS_ICON_PID = 100, 101
RENDER_TAIL_STEP = 2


class PatchError(RuntimeError):
    """The input APK does not match the reference layout, or cannot be patched safely."""


# ---------------------------------------------------------------- 基础工具
def varint(value: int) -> bytes:
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def xor_table(blob: bytes) -> bytes:
    """Re-apply 的定位异或(convert_data_bytes 的第二段, 对合)。"""
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
    """4 顶点 / 20 B 每顶点(位置 float32x3 + UV float32x2)。

    顶点顺序与索引缓冲照抄原版图集里的四边形 Sprite; UV 通道全 0(引擎按
    textureRect / uvTransform 取图, 原版所有 Sprite 都是 0)。
    """
    hw, hh = width / 200.0, height / 200.0
    out = bytearray()
    for x, y in ((hw, -hh), (-hw, -hh), (-hw, hh), (hw, hh)):
        out += struct.pack("<fffff", x, y, 0.0, 0.0, 0.0)
    return bytes(out)


QUAD_INDEX_BUFFER = [1, 0, 2, 0, 3, 0, 0, 0, 1, 0, 3, 0]


def hashed_render_key(path: str) -> list[int]:
    digest = hashlib.md5(path.encode("utf-8")).digest()  # noqa: S324 - 资源键, 非安全用途
    return [int.from_bytes(digest[i * 4:i * 4 + 4], "little") for i in range(4)]


def render_tail(keys: list[int]) -> int:
    """同文件里未用的下一个 render key 尾号(原版按 2 递增)。"""
    return max(keys) + RENDER_TAIL_STEP if keys else 21300000


def texture_rect(box: tuple[int, int, int, int], image_height: int) -> tuple[int, int, int, int]:
    """左上原点裁剪框 -> 贴图(自下而上)坐标的 (x, y, width, height)。"""
    x0, y0, x1, y1 = box
    return x0, image_height - y1, x1 - x0, y1 - y0


# ---------------------------------------------------------------- 资源树构造
def texture_tree(template: dict, name: str, image) -> dict:
    """照抄同文件既有 Texture2D, 只改名字 / 尺寸 / 格式 / 像素数据。"""
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
    """把 Sprite 的取图区 / 四边形网格改到 rect; 网格计数必须与四边形自洽。"""
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


def sprite_tree(template: dict, name: str, texture_pid: int, rect, key, tail: int) -> dict:
    tree = copy.deepcopy(template)
    tree["m_Name"] = name
    tree["m_Border"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0}
    tree["m_Pivot"] = {"x": 0.5, "y": 0.5}
    tree["m_Extrude"] = 1
    tree["m_IsPolygon"] = False
    tree["m_RenderDataKey"] = [dict(zip(("data[0]", "data[1]", "data[2]", "data[3]"), key)), tail]
    tree["m_AtlasTags"] = []
    tree["m_SpriteAtlas"] = {"m_FileID": 0, "m_PathID": 0}
    place_sprite(tree, texture_pid, rect)
    return tree


# ---------------------------------------------------------------- SerializedFile 读写
def load_serialized(blob: bytes):
    import UnityPy

    environment = UnityPy.load(blob)
    return next(iter(environment.files.values()))


def objects(serialized) -> list:
    values = serialized.objects
    return list(values.values()) if isinstance(values, dict) else list(values)


def read_entry(apk: Path, entry: str) -> bytes:
    with zipfile.ZipFile(apk) as archive:
        try:
            return archive.read(DATA_PREFIX + entry)
        except KeyError as exc:
            raise PatchError(f"{apk} is missing {DATA_PREFIX}{entry}") from exc


def serialise_tree(serialized, class_id: int, tree: dict) -> bytes:
    from UnityPy.helpers.Tpk import get_typetree_node
    from UnityPy.helpers.TypeTreeHelper import write_typetree
    from UnityPy.streams import EndianBinaryWriter

    node = get_typetree_node(class_id, serialized.version)
    writer = EndianBinaryWriter(endian=serialized.header.endian)
    write_typetree(tree, node, writer, serialized)
    return writer.bytes


def add_object(serialized, path_id: int, class_id: int, tree: dict) -> None:
    """追加一个新对象; 该文件必须已经含有同 class 的既有对象作为类型模板。"""
    from UnityPy.enums import ClassIDType
    from UnityPy.files import ObjectReader

    for type_id, serialized_type in enumerate(serialized.types):
        if serialized_type.class_id == class_id:
            break
    else:
        raise PatchError(f"serialized file has no class {class_id} template")
    raw = serialise_tree(serialized, class_id, tree)
    serialized.objects[path_id] = ObjectReader(
        serialized, None, path_id, type_id, serialized_type, class_id,
        ClassIDType(class_id), 0, len(raw), None, None, data=raw)


def container_file_id(serialized, key: str, expected: str) -> int:
    """容器条目 m_FileID 是 1 基下标: externals[m_FileID - 1] 才是目标文件。"""
    resource_manager = next((o for o in objects(serialized) if o.class_id == RESOURCE_CLASS), None)
    if resource_manager is None:
        raise PatchError("globalgamemanagers holds no ResourceManager")
    container = resource_manager.read_typetree()["m_Container"]
    values = [value for name, value in container if name == key]
    if not values:
        raise PatchError(f"container has no {key!r} entry to copy the file index from")
    file_ids = {value["m_FileID"] for value in values}
    if len(file_ids) != 1:
        raise PatchError(f"{key!r} entries disagree on m_FileID")
    file_id = file_ids.pop()
    external = serialized.externals[file_id - 1]
    resolved = getattr(external, "path", None) or getattr(external, "name", None)
    if resolved != expected:
        raise PatchError(f"externals[{file_id - 1}] is {resolved!r}, expected {expected!r}")
    return file_id


# ---------------------------------------------------------------- A. 载体立绘
def patch_carrier(apk: Path, drawing) -> tuple[bytes, dict]:
    serialized = load_serialized(read_entry(apk, CARRIER))
    existing = objects(serialized)
    texture_template = next(o.read_typetree() for o in existing if o.class_id == TEXTURE_CLASS)
    sprite_template = next(o.read_typetree() for o in existing if o.class_id == SPRITE_CLASS)
    used = {o.path_id for o in existing}
    new_ids = (CARRIER_TEXTURE_PID, CARRIER_DRAWING_PID, CARRIER_HALF_ICON_PID)
    if used & set(new_ids):
        raise PatchError(f"carrier already uses path ids {sorted(used & set(new_ids))}")
    tails = [o.read_typetree()["m_RenderDataKey"][1] for o in existing
             if o.class_id == SPRITE_CLASS]
    drawing_tail, half_tail = render_tail(tails), render_tail(tails) + RENDER_TAIL_STEP

    width, height = drawing.size
    whole = (0, 0, width, height)
    card = texture_rect(CARD_BOX, height)
    add_object(serialized, CARRIER_TEXTURE_PID, TEXTURE_CLASS,
               texture_tree(texture_template, DRAWING, drawing))
    add_object(serialized, CARRIER_DRAWING_PID, SPRITE_CLASS,
               sprite_tree(sprite_template, DRAWING, CARRIER_TEXTURE_PID, whole,
                           hashed_render_key(DRAWING_KEY), drawing_tail))
    # 卡片主图(HalfDrawing)复用同一张贴图, 只多一个 Sprite 对象, 不额外占体积。
    add_object(serialized, CARRIER_HALF_ICON_PID, SPRITE_CLASS,
               sprite_tree(sprite_template, HALF_ICON, CARRIER_TEXTURE_PID, card,
                           hashed_render_key(HALF_ICON_KEY), half_tail))
    payload = serialized.save()

    # 自检: 回读像素 + 网格自洽 + 既有对象保留
    check = load_serialized(payload)
    textures = {o.path_id: o for o in objects(check) if o.class_id == TEXTURE_CLASS}
    sprites = {o.path_id: o for o in objects(check) if o.class_id == SPRITE_CLASS}
    if sorted(textures) != [1, CARRIER_TEXTURE_PID] or 2 not in sprites:
        raise PatchError("carrier lost its original objects")
    back = textures[CARRIER_TEXTURE_PID].parse_as_object().image
    if back.size != drawing.size or back.convert("RGBA").tobytes() != drawing.tobytes():
        raise PatchError("carrier drawing texture is not pixel identical")
    for path_id, name, rect in ((CARRIER_DRAWING_PID, DRAWING, whole),
                                (CARRIER_HALF_ICON_PID, HALF_ICON, card)):
        tree = sprites[path_id].read_typetree()
        render_data = tree["m_RD"]
        if tree["m_Name"] != name or render_data["texture"] != {"m_FileID": 0, "m_PathID": 1000}:
            raise PatchError(f"carrier sprite {path_id} is not bound to the new texture")
        mesh = render_data["m_SubMeshes"][0]
        if mesh["indexCount"] != 6 or len(render_data["m_IndexBuffer"]) != 12:
            raise PatchError(f"carrier sprite {path_id} quad mesh is inconsistent")
        want = {"x": float(rect[0]), "y": float(rect[1]),
                "width": float(rect[2]), "height": float(rect[3])}
        if render_data["textureRect"] != want:
            raise PatchError(f"carrier sprite {path_id} textureRect is "
                             f"{render_data['textureRect']}")
    return payload, {"texture": CARRIER_TEXTURE_PID, "sprites": [CARRIER_DRAWING_PID,
                                                                CARRIER_HALF_ICON_PID],
                     "card_box": list(CARD_BOX), "image": [width, height]}


# ---------------------------------------------------------------- B. 图集头像
def patch_atlas(apk: Path, head_icon) -> tuple[bytes, dict]:
    serialized = load_serialized(read_entry(apk, ATLAS))
    existing = objects(serialized)
    texture_template = next(o.read_typetree() for o in existing if o.class_id == TEXTURE_CLASS)
    used = {o.path_id for o in existing}
    if used & {ATLAS_TEXTURE_PID, ATLAS_ICON_PID}:
        raise PatchError("skinhead01 already uses the reserved path ids")
    sprites = [o for o in existing if o.class_id == SPRITE_CLASS]
    # 挑一个 4 顶点四边形作模板, 免得再从 Tight 网格改写索引。
    templates = [o.read_typetree() for o in sprites]
    quad_templates = [t for t in templates if t["m_RD"]["m_SubMeshes"][0]["vertexCount"] == 4]
    if not quad_templates:
        raise PatchError("skinhead01 has no four-vertex sprite to copy")
    tail = render_tail([t["m_RenderDataKey"][1] for t in templates])
    shared_key = list(quad_templates[0]["m_RenderDataKey"][0].values())

    add_object(serialized, ATLAS_TEXTURE_PID, TEXTURE_CLASS,
               texture_tree(texture_template, HEAD_ICON, head_icon))
    add_object(serialized, ATLAS_ICON_PID, SPRITE_CLASS,
               sprite_tree(quad_templates[0], HEAD_ICON, ATLAS_TEXTURE_PID,
                           (0, 0, head_icon.width, head_icon.height), shared_key, tail))
    payload = serialized.save()

    check = load_serialized(payload)
    textures = {o.path_id: o for o in objects(check) if o.class_id == TEXTURE_CLASS}
    added = next(o for o in objects(check) if o.class_id == SPRITE_CLASS
                 and o.path_id == ATLAS_ICON_PID)
    if len([o for o in objects(check) if o.class_id == SPRITE_CLASS]) != len(sprites) + 1:
        raise PatchError("skinhead01 sprite count changed by more than one")
    back = textures[ATLAS_TEXTURE_PID].parse_as_object().image
    if back.size != head_icon.size or back.convert("RGBA").tobytes() != head_icon.tobytes():
        raise PatchError("skinhead01 icon texture is not pixel identical")
    tree = added.read_typetree()
    if tree["m_Name"] != HEAD_ICON or tree["m_RD"]["texture"] != {"m_FileID": 0,
                                                                  "m_PathID": ATLAS_TEXTURE_PID}:
        raise PatchError("skinhead01 icon sprite is not bound to the new texture")
    return payload, {"texture": ATLAS_TEXTURE_PID, "sprite": ATLAS_ICON_PID,
                     "image": [head_icon.width, head_icon.height], "tail": tail}


# ---------------------------------------------------------------- C. gg 容器
def patch_container(apk: Path) -> tuple[bytes, dict]:
    serialized = load_serialized(read_entry(apk, GLOBAL))
    resource_manager = next((o for o in objects(serialized) if o.class_id == RESOURCE_CLASS), None)
    if resource_manager is None:
        raise PatchError("globalgamemanagers holds no ResourceManager")
    carrier_file = container_file_id(serialized, DRAWING_SOURCE_KEY, CARRIER)
    atlas_file = container_file_id(serialized, ATLAS_GROUP, ATLAS)
    tree = resource_manager.read_typetree()
    container = list(tree["m_Container"])
    keys = [key for key, _ in container]
    if any(key.isupper() for key in keys):
        raise PatchError("container keys are not all lowercase")
    if keys != sorted(keys):
        raise PatchError("container is not sorted")
    # 'uialtas/altas/skinhead01' 在原版容器里已有一组(35 条), 本工具在组末尾补 1 条;
    # 另两个 skindrawing / heroicon_h 键是全新的, 必须不存在。
    group_before = [value["m_PathID"] for name, value in container if name == ATLAS_GROUP]
    if not group_before:
        raise PatchError(f"container lacks {ATLAS_GROUP!r} group")
    if any(value["m_FileID"] != atlas_file for name, value in container if name == ATLAS_GROUP):
        raise PatchError(f"{ATLAS_GROUP!r} group entries disagree on m_FileID")
    for key in (HALF_ICON_KEY, DRAWING_KEY):
        if key in keys:
            raise PatchError(f"container already has {key!r}")
    additions = [(ATLAS_GROUP, atlas_file, [ATLAS_ICON_PID]),
                 (HALF_ICON_KEY, carrier_file, [CARRIER_TEXTURE_PID, CARRIER_HALF_ICON_PID]),
                 (DRAWING_KEY, carrier_file, [CARRIER_TEXTURE_PID, CARRIER_DRAWING_PID])]
    inserted = []
    for key, file_id, path_ids in additions:
        # 容器严格按路径有序(同键条目相邻), 新条目插在「第一个大于它的键」之前,
        # 否则二分查找区间被破坏, 会连带其它资源查不到。ATLAS_GROUP 已存在,
        # 其插点落在该组末尾, 等价于往组内追加。
        position = next((i for i, name in enumerate(keys) if name > key), len(container))
        container[position:position] = [(key, {"m_FileID": file_id, "m_PathID": path_id})
                                        for path_id in path_ids]
        keys = [name for name, _ in container]
        inserted.append({"key": key, "index": position, "path_ids": path_ids, "file_id": file_id})
    if keys != sorted(keys):
        raise PatchError("container lost its ordering")
    tree["m_Container"] = container
    resource_manager.save_typetree(tree)
    payload = serialized.save()

    check = load_serialized(payload)
    manager = next(o for o in objects(check) if o.class_id == RESOURCE_CLASS)
    after = manager.read_typetree()["m_Container"]
    after_keys = [key for key, _ in after]
    if len(after) != len(container) or after_keys != sorted(after_keys):
        raise PatchError("patched container is malformed")
    group_after = [value["m_PathID"] for name, value in after if name == ATLAS_GROUP]
    if group_after != group_before + [ATLAS_ICON_PID]:
        raise PatchError(f"container {ATLAS_GROUP!r} -> {group_after}, "
                         f"expected {group_before + [ATLAS_ICON_PID]}")
    expect = {DRAWING_KEY: [CARRIER_TEXTURE_PID, CARRIER_DRAWING_PID],
              HALF_ICON_KEY: [CARRIER_TEXTURE_PID, CARRIER_HALF_ICON_PID]}
    for key, path_ids in expect.items():
        got = [value["m_PathID"] for name, value in after if name == key]
        if got != path_ids:
            raise PatchError(f"container {key!r} -> {got}, expected {path_ids}")
    return payload, {"inserted": inserted, "entries": len(after),
                     "atlas_group": len(group_after)}


# ---------------------------------------------------------------- D/E. 权威表
def split_array(plain: bytes):
    """拆 (4B 计数 + 全部 key + 全部行) 的表结构: (count, keys, rows, spans, keys_end)。"""
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
        out += b"\x12" + varint(len(row)) + row
    return bytes(out)


def field_span(row: bytes, number: int, wire: int) -> tuple[int, int, object]:
    hits = [value for value in parse_message(row)[0] if value.field == number]
    if len(hits) != 1 or hits[0].wire != wire:
        raise PatchError(f"expected exactly one field {number} of wire type {wire}")
    return hits[0].start, hits[0].end, hits[0].value


def reencrypt(encrypted: bytes, plain: bytes, prefix: bytes) -> bytes:
    obfuscated = xor_table(plain)
    if obfuscated[:len(prefix)] != prefix:
        raise PatchError("the RSA-covered prefix would change")
    patched = encrypted[:128] + obfuscated[len(prefix):]
    if convert_data_bytes(patched) != plain:
        raise PatchError("re-encryption round trip failed")
    return patched


def patch_appearance(encrypted: bytes) -> tuple[bytes, dict]:
    table = parse_table_container(encrypted)
    if table["kind"] != "array":
        raise PatchError("Appearance is not a key/row array")
    plain, prefix = table["plain"], rsa_public_unpad(encrypted[:128])
    count, keys, rows, spans, keys_end = split_array(plain)
    index = keys.index(APPEARANCE_ID)
    if spans[index] < len(prefix):
        raise PatchError("the 1223003 row sits inside the RSA-covered prefix")
    row = rows[index]

    start, end, value = field_span(row, 15, 2)
    if value != SPINE_SHOW:
        raise PatchError(f"Appearance 1223003 SpineShow is {value!r}")
    row = row[:start] + b"\x7a\x00" + row[end:]
    start, end, value = field_span(row, 29, 0)
    if value != MAIN_PAINTING_SCALE_OLD:
        raise PatchError(f"Appearance 1223003 MainPaintingScale is {value!r}")
    row = row[:start] + varint(29 << 3) + varint(MAIN_PAINTING_SCALE_NEW) + row[end:]
    rows[index] = row

    repaired = build_array(plain, keys_end, rows)
    patched = reencrypt(encrypted, repaired, prefix)
    decoded = parse_table_container(patched)
    row = decoded["items"][decoded["keys"].index(APPEARANCE_ID)]
    if field_span(row, 15, 2)[2] not in (b"", None):
        raise PatchError("SpineShow was not cleared")
    if field_span(row, 29, 0)[2] != MAIN_PAINTING_SCALE_NEW:
        raise PatchError("MainPaintingScale was not rewritten")
    return patched, {"spine_show": "cleared",
                     "main_painting_scale": [MAIN_PAINTING_SCALE_OLD, MAIN_PAINTING_SCALE_NEW]}


def patch_unit_base(encrypted: bytes) -> tuple[bytes, dict]:
    table = parse_table_container(encrypted)
    if table["kind"] != "array":
        raise PatchError("UnitBase is not a key/row array")
    plain, prefix = table["plain"], rsa_public_unpad(encrypted[:128])
    count, keys, rows, spans, keys_end = split_array(plain)
    index = keys.index(UNIT_ID)
    if spans[index] < len(prefix):
        raise PatchError("the 1030 row sits inside the RSA-covered prefix")
    row = rows[index]
    listed = [value for value in parse_message(row)[0] if value.field == 48]
    if [value.value for value in listed] != UNIT_APPEARANCE_LIST_OLD:
        raise PatchError(f"UnitBase 1030 AppearanceList is {[v.value for v in listed]}")
    if APPEARANCE_ID in [value.value for value in listed]:
        raise PatchError("UnitBase 1030 already lists 1223003")
    rows[index] = row + varint(48 << 3) + varint(APPEARANCE_ID)

    repaired = build_array(plain, keys_end, rows)
    patched = reencrypt(encrypted, repaired, prefix)
    decoded = parse_table_container(patched)
    row = decoded["items"][decoded["keys"].index(UNIT_ID)]
    after = [value.value for value in parse_message(row)[0] if value.field == 48]
    if after != UNIT_APPEARANCE_LIST_OLD + [APPEARANCE_ID]:
        raise PatchError(f"AppearanceList after patch is {after}")
    return patched, {"appearance_list": UNIT_APPEARANCE_LIST_OLD + [APPEARANCE_ID]}


def split_raw_text_asset(raw: bytes, table: str) -> tuple[bytes, bytes]:
    """TextAsset 的原始对象字节 -> (name 头, 旧 m_Script)。

    布局: [4B m_Name 长度][m_Name][补齐到 4][4B m_Script 长度][m_Script]
    ★ 不能用 read_typetree: UnityPy 会把 m_Script 当 utf-8 解码, 往返破坏二进制密文。
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
    patched, audit = repair(encrypted)
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
    audit["encrypted_bytes"] = [len(encrypted), len(again)]
    return payload, audit


# ---------------------------------------------------------------- 主流程
def patch(apk: Path, skin: Path, output: Path) -> dict[str, str]:
    from PIL import Image

    output.mkdir(parents=True, exist_ok=True)
    drawing = Image.open(skin).convert("RGBA")
    if drawing.size != (1980, 2048):
        raise PatchError(f"expected a 1980x2048 drawing, got {drawing.size}")
    head_icon = drawing.crop(HEAD_BOX).resize((HEAD_ICON_SIZE, HEAD_ICON_SIZE), Image.LANCZOS)

    steps = (
        (CARRIER, lambda: patch_carrier(apk, drawing)),
        (ATLAS, lambda: patch_atlas(apk, head_icon)),
        (GLOBAL, lambda: patch_container(apk)),
        (APPEARANCE_TABLE, lambda: rebuild_table(apk, APPEARANCE_TABLE, "Appearance",
                                                 patch_appearance)),
        (UNIT_BASE_TABLE, lambda: rebuild_table(apk, UNIT_BASE_TABLE, "UnitBase",
                                                patch_unit_base)),
    )
    manifest: dict[str, str] = {}
    audit: dict[str, dict] = {}
    for entry, build in steps:
        payload, record = build()
        target = output / (entry + ".bin")
        target.write_bytes(payload)
        manifest[DATA_PREFIX + entry] = str(target.resolve())
        audit[DATA_PREFIX + entry] = record
        print("%-52s %8d B" % (entry, len(payload)))
    (output / "patches.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"patched {len(manifest)} assets; RSA prefixes and untouched objects are preserved")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--skin", type=Path, default=DEFAULT_SKIN)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    patch(arguments.apk, arguments.skin, arguments.output)
