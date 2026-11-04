---
Document-Type: Compatibility Decision
Domain: Favorability / Appearance
Status: ACTIVE
Updated: 2026-11-04
---
# Decision
把 2.4 客户端关掉的「契约(花嫁)」系统整条恢复，并与服务端
[src/x2server/player/date.py](../../../src/x2server/player/date.py) /
[favor.py](../../../src/x2server/player/favor.py) 对齐：

- 好感度上限从 10 / 19 级提高到 20 级；FavorabilityLevel 19 行补
  `IsCovenant=1` 与信物 `[1204011, 1]`。
- 25 个可约会神格（1003..1024、1197..1199）恢复两条约会与 18 个契约碎片；
  非初玖的 24 位神格只走通用约会流程，客户端不再显示契约拼图页。
- 涂山初玖（hero 1010）恢复契约形象 Appearance `1221004`，含花嫁立绘、
  头像、道具、图鉴、互动热区与 UnitBase 外观列表。
- 契约说明页文案 `13430051..13430054` 从 1.0 包补回。

客户端侧用一个自包含工具
[tools/patch_contract_chujiu.py](../../../tools/patch_contract_chujiu.py) 完成表、美术、
`libil2cpp.so` 三块补丁。素材随本 PR 提供，使用方不需要再从旧包/私服目录里找文件。

# Reason
2.4 客户端保留了 `FavorDateModule` 代码，但数据和资源被整体裁掉，只补服务端不够：

- FavorabilityHero 25 行的 `LevelLimit` 仍是 10，服务端把等级开放到 20 后客户端成长条 /
  突破按钮会在 10 级封顶。
- FavorabilityLevel 19 没有 `IsCovenant` 与 `CovenantItem`，契约入口不出现。
- FavorabilityDate 里初玖的 101001 / 101002 只剩 `f1/f3/f8=2` 的空壳；其余 24 位神格
  根本没有约会行。OptionEffect 也缺 480 条碎片 / 约会选项。
- Appearance 1221004、Item 1221004 / 1271004、Picture 1271004、
  ExpressionInteractiveArea 1221004、UnitBase 1010 的 `AppearanceList` 全缺，契约后
  没有形象可切。
- 1.0 包里的 5 个美术 bundle 没有注册进 `globalgamemanagers` 的
  `ResourceManager.m_Container`，即使表里写了资源键也只会拿到空引用。
- 表会从「128 B RSA 头 + 密文尾部」变成明文，长度也变了；客户端
  `LogicX2.Resources.ConvertDataBytes` 必须旁路这 10 张表，否则解析失败。

# Scope
工具只读参考 APK，把所有产物写到 `--output`，不回写输入。

## A. 表补丁（10 张 TextAsset）
明文写入 `m_Script`，保留 TextAsset 原有的 `m_Name` 头；每张表写完都回读校验行数 /
  行内容 / 16 B 前缀 sig。

| 表 | 改动 |
| --- | --- |
| `FavorabilityHero` | 25 个神格 `f3 LevelLimit` 10 -> 20 |
| `FavorabilityLevel` | 19 行追加 `f6 IsCovenant=1`、`f7 CovenantItem=[1204011,1]` |
| `FavorabilityDate` | 25 个神格 × 2 条：初玖沿用 1.0 的剧本/背景/坐标；其余复用 8 张现有 CG |
| `OptionEffect` | 24 个非初玖神格 × (18 碎片 + 2 约会选项) = 480 条 |
| `Appearance` | 克隆 1221005（初玖泳装）-> 1221004 契约形象；`f12` 指向 304x512 详情立绘 |
| `Item` | 新增 1221004（外观道具，type 17）与 1271004（花嫁头像，type 22） |
| `Picture` | 新增 1271004，复用 `MarryHead01/Hero_Icon_101004` |
| `ExpressionInteractiveArea` | 克隆 1221003 热区 -> 1221004 |
| `UnitBase` | 1010 的 `f48 AppearanceList` 追加 1221004 |
| `Language` | 补 13430051..13430054 四条契约说明页文案 |

## B. 美术注入（5 个 bundle + globalgamemanagers）
- `05a68fcc…`（`uialtas/altas/chujiu_marry`，19 条：1 贴图 + 18 碎片小图）
- `7baf99e6…`（`uialtas/altas/covenant`，2 条）
- `5f3a0a68…`（`uialtas/altas/marryhead01`，2 条）
- `d3b1e7dd…`（`uialtas/heroicon_h/hero_icon_101004_h`，2 条）
- `06d6762c…`（`uialtas/marrydrawing/marrydrawing_1221004`，2 条）——工具在构建时追加
  Texture2D `pid 1000` + Sprite `pid 1001` `MarryDrawing_1221004_Detail`（304x512，
  从 1864x2048 花嫁整图居中裁出），并把整幅画面缩到 66% 居中、同图模糊铺底；画布尺寸
  保持 1864x2048，详情页取景不变。
- `globalgamemanagers`：externals 只追加 5 条（fileID 7922..7926），容器插入 6 个键 /
  29 条目，全部小写且严格有序；既有 m_FileID 不变。

## C. libil2cpp.so（固定偏移 + 原指令断言）
| 偏移 | 改动 |
| --- | --- |
| `0x1B4A0C4` | `b OLD_CAVE` -> `b 0x42B3AD8`，前缀明文旁路 payload（2 条基包 sig + 10 张表 sig，共 12 条） |
| `0x1AAA334` | 完成度 `bl 0x1AA5AE0` -> `bl 0x1AA59EC`（按已收集碎片 / 碎片总数） |
| `0x1AA811C` / `0x1AA87C0` | `bl CheckMarried` -> 辅助函数；仅 1010 返回真值，其余 24 神格不再显示契约拼图页 |

每个点都先读原指令并断言；偏移处不是预期指令时直接报错，不会静默写坏 .so。工具还会
重解析 payload、校验 12 条前缀、bl/b 目标、零区与辅助函数尾部，并保留重复运行不叠加的
语义（已在补丁后的表 / .so 上回放验证，产物逐字节相同）。

# Official
NO（官方 1.0 有完整契约系统，2.4 客户端裁掉了数据与美术；本补丁是按官方旧包恢复的
兼容决定，不是官方 2.4 行为）

# User-authorized
YES（USER_DECISION，2026-11-04）

# Usage
```powershell
python tools\patch_contract_chujiu.py --apk <reference.apk> --output <dir>
# 可选：改花嫁整幅 CG 的缩放比例（默认 0.66，只影响 06d6762c… 整图，不影响详情立绘）
python tools\patch_contract_chujiu.py --apk <reference.apk> --output <dir> --marry-scene-ratio 0.66
```

输出目录中是可替换同名 zip 条目的文件（文件名 = 原条目名 + `.bin`）：

- `assets/bin/Data/` 下 10 张表、5 个美术 bundle、`globalgamemanagers.bin`
- `libil2cpp.so.bin`
- `patches.json`（zip 条目 -> 产物路径）与 `audit.json`（每处改动明细）

替换后必须用本地开发密钥重新签名才能安装；工具不做 reseal，也不安装到设备。

# Notes
- **素材随 PR 提供，无需自行准备。** `tools/assets/contract/` 已包含全部输入
  （合计约 4.5 MB）；没有 88 MB 的 `libil2cpp.so.bin`、2 GB APK 或 reseal 后的成品。
- 素材清单（`tools/assets/contract/`）：

  | 文件 | 大小 | SHA-256 | 来源 |
  | --- | --- | --- | --- |
  | `05a68fcce3dd15c4b80bc28ed86f9d33.bin` | 536,264 B | `129d77fa79985ea3c4a0ad8d0971a27d8ca433e2a713c62ac903a9c8a384ca14` | 旧包 `com.siva.project.x2-5.apk` 的 `assets/bin/Data/05a68fcc…` |
  | `7baf99e6e7940604bb5a4ba44150959e.bin` | 70,456 B | `1e07da273038ff7337c80e1611048b495f5f8d2e136fe66e483b71b76c78c48d` | 旧包 `assets/bin/Data/7baf99e6…` |
  | `5f3a0a68a4b8e7943a375fb814d67fc2.bin` | 71,092 B | `bdd6b84c3521a9954bf0c92b50aa271466c8b6b07c8c84b71900cc590db49c7c` | 旧包 `assets/bin/Data/5f3a0a68…` |
  | `d3b1e7dd001810a408e1412ab4903fa2.bin` | 133,660 B | `ced9d94fa52d4fdbe990b4c3041f2c80b7bbb1f1221e09d31b80b2a36c592d27` | 旧包 `assets/bin/Data/d3b1e7dd…` |
  | `06d6762cd0bf8914c8b140e93fc5d846.bin` | 3,858,220 B | `c703fdeaee687ba1dde887164a1502f5dd68338989f1efa2fc77e1ff0807d97a` | 旧包 `assets/bin/Data/06d6762c…`（原始花嫁 bundle；详情立绘与 0.66 缩放在工具里现场生成） |
  | `table_sigs.json` | 1,306 B | `60be936102a8c9c11e2ce4b4562841ce8864435c43f1f866f39b71d34f34ebf6` | 参考包补丁后 10 张表的 16 B 前缀 sig；用于校验 APK 版本 |
  | `language_13430051_54.json` | 1,210 B | `8816da88514fee15505b749655ea1f12c27592eb06891bf9c999a5160d6170fa` | 旧包 `Language.bin` 的 13430051..54 中文列 |

- 参考包上产出的 5 个美术 bundle / `globalgamemanagers` / `libil2cpp.so` SHA-256（默认
  0.66，供人工核对）：

  | 条目 | 大小 | SHA-256 |
  | --- | --- | --- |
  | `05a68fcc…` | 536,264 B | `129d77fa79985ea3c4a0ad8d0971a27d8ca433e2a713c62ac903a9c8a384ca14` |
  | `7baf99e6…` | 70,456 B | `1e07da273038ff7337c80e1611048b495f5f8d2e136fe66e483b71b76c78c48d` |
  | `5f3a0a68…` | 71,092 B | `bdd6b84c3521a9954bf0c92b50aa271466c8b6b07c8c84b71900cc590db49c7c` |
  | `d3b1e7dd…` | 133,660 B | `ced9d94fa52d4fdbe990b4c3041f2c80b7bbb1f1221e09d31b80b2a36c592d27` |
  | `06d6762c…` | 15,929,896 B | `a0bb13f414885e1a7e80ae9d750508c5039d088d0abc3efd1183f498bdba2d05` |
  | `globalgamemanagers` | 21,866,256 B | `18a6bcd9bf2deab986aa03b9d974ca9233f60dcd1e98b4a135876ec8487e456e` |
  | `libil2cpp.so` | 88,855,552 B | `9af10c003efffb1ba836c88925c8ae4dc9a5200af5ba317065225082b1b68977` |

- 工具必须以含上述摘要的参考基包为输入。`table_sigs.json` 的 16 B 前缀与
  `EXPECTED_BASE_SIGS` 是版本闸门：表结构或 .so 布局不符会明确报错。
- 已知限制：其余 24 位神格约会页没有专属 CG，复用现有 8 张（密使街 / 魔都 / 魔都 2 /
  魔都夜玩 / 魔都雨 / 魔都黄昏 / 篝火店 / 街道）；契约拼图页由 .so 辅助函数对非 1010
  隐藏，因此这 24 位只走通用约会，不进入契约线。
- `--marry-scene-ratio` 只影响花嫁整幅 CG 的留白比例；详情立绘 `pid 1001` 始终是
  304x512。默认 0.66 与现役私服产物逐字节一致。
- 服务端改动（20 级上限、约会目录、契约道具、1010 外观）必须同时生效；只打客户端补丁
  不会放开等级或发放契约形象。
- 不提交 `.bin` 产物（表 + 美术 + .so 合计约 130 MB）到 Git；工具 + 素材足以复现。
