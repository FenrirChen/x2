# 秘宝之海战斗、守卫战与 CG 修复

## 已撤回

2026-10-11 用户要求撤回此活动。服务端移除秘宝之海的开放配置并关闭全部相关关卡；客户端恢复 `X2-Revival-ActivityUI-Local-signed.apk` 与 `X2-Revival-ActivityUI-Remote-signed.apk`。Treasure / Treasure-R2 包不再作为发布版本。下面仅保留研究记录，不代表当前客户端或活动已启用。

## 20:28 用户复测失败后的二次修复（R2，待用户验收）

用户反馈上一轮问题均未解决。ADB 核对模拟器 base.apk 的 SHA256 为
2f6e24fef86fbde8695ee586f0b1317246710a08439ab60be7eb61697bab10f2，
与上一轮 Treasure-Local 签名包一致，排除安装错版本。
最新 Unity 日志 runtime/activity_recheck_unity.log 在 20:28:08 报
BattleX2.ChangeSceneShow / OnCreateLevel 的 List.get_Item 越界；另有
Image.get_mainTexture 的材质缺失 _MainTex 异常。服务端 2160911 的
FightData 返回 code=10，但这不证明客户端能进入战斗。

- 入口：MainPage.OnHandleActivitySync 启用主题按钮后不调用 ResetButtonPos；
  OnOpen、OnInit、OnShow 才重算世界节点对应的 UI 点击区域。R2 在异步刷新末尾
  先保留 InitMainPageEffectEnter，再调用 ResetButtonPos（0x13DBC80 -> 0x42B0A00）。
  上一轮只修改 openDes/lockDes 的显隐，无法修复点击区域位置。
- 材质：Image 无 Sprite 的分支直接读取装饰材质的 mainTexture；ui_mibao07 等
  使用 _A_tex 的原材质没有 _MainTex。R2 仅在 Image 的这次读取处先检查
  HasProperty，缺失时使用原有白纹理分支；保留有 _MainTex 的读取行为，
  不修改全局 Material API（0x2A56350 -> 0x42B0A40）。
- CG：主页 BGImg 841、关卡 BGImg 403 为宽1688、高0，上一轮的“两个尺寸均为0”
  检查遗漏了它们。补齐高度950.1317；五页九个 CG 节点使用 Simple 图像绘制，
  关闭 AdvancedImage.useSpriteMesh，避免保留 CG 的零 UV 自定义网格影响显示。
- 场地：APK 的所有内置场景均无 X2_byxy_tafang_01–06 模型；只有原寻路、
  碰撞和路线配置。上一轮只补 scenelogic，GetRoomObj 仍找不到显示对象，
  OnCreateLevel 跳过加入显示列表，随后 ChangeSceneShow 按逻辑房间数越界。
  R2 从原 Detour VAND v7 数据的多边形生成六张显示用地面网格，追加到
  level5 的 StandardCell 模板根，绑定原白夜学院地面材质。六张网格分别
  26/46/49/69/40/66 顶点、24/44/47/67/38/64 三角形。没有替换寻路、碰撞、
  波次、塔控制器或怪物数据。这是兼容地面，不是恢复已缺失的官方装饰模型。

工具：tools/savemanager/client/patch_activity_followup.py；构建、对象审计在
tools/savemanager/client/build/activity_followup。rebuild_existing_apk.py 可从
已有存档管理 APK 应用补丁，不重复追加 DEX 或桥接库，也不依赖消失的旧基线。
网格经 UnityPy MeshHandler 解码、所有新组件 PPtr 相互对应、level5 原对象除
StandardCell 子列表外逐字节保持。相关服务端测试 3 passed / 44 deselected。
发行包为 X2-Revival-Treasure-R2-Local-signed.apk 与 R2-Remote-signed.apk。
仍交给用户手动验收；静态解析、签名和服务端测试不等同于游戏内通过。

两份 R2 包正式证书 v1/v2/v3 验证、完整 ZIP CRC 和 stored 条目对齐通过；
两版非签名内容仅 GameConfig 不同，相对于上一版本地包正好7个内容条目变化。
MuMu 已通过 adb install -r 覆盖安装本地 R2（保留应用数据），随后读取安装位置
并核验 SHA256=854ea23116f62621b8c70aed69f462107431296cf0a54a32935b26d9cb63d0d1。
没有打开游戏或代替用户进行界面验收。核验记录 runtime/activity_r2_release_check.json。

本地服务端 20:46:40 重启，数据库备份
runtime/before_activity_ui_followup_20261011_204640.sqlite3；仍开放秘宝之海。
下方为上一轮记录，其中“33个PrefabPath在scenelogic字典中”的检查仅覆盖逻辑
数据，未覆盖可见模型，不能再作为客户端场景完整的证据。

## 日志证据

本地日志 activity_ui_followup_20261011_195710.err.log：2160913 战斗请求返回 code=10；921 QueryActivityTower、925 ActivityTowerPassive 被通用活动处理器拒绝。Unity logcat 在 19:59:53 报 LogicX2.BaseLevel.InitPhysical 空引用。

## 客户端

- 之前的 SceneMap 兼容别名同时改变 scenelogic 的选择。普通白夜学院缺少 X2_byxy_tafang_01 至 06 等专用房间数据，房间初始化后物理对象为空。
- 将 APK 保留的塔防 scenelogic 中缺失的房间键追加到对应替代场景的字典。已有键及普通门、Boss 房间原始数据逐字节保留。白夜学院追加 10 键；金字塔追加 8 键。
- 读取当前活动 SceneBase 和 ComponentBase 配置，核对 33 个场景配置所需的 PrefabPath 全部在修复后的白夜学院 scenelogic 字典中。
- GameRoomInfo.get_RoomTriggerGroup（0x1E5B6B8）对缺失触发器列表返回初始化后的空 List<TriggerGroup>，保留已有触发器；原生差异仅 getter 分支和 0x42B0900 洞位。泛型元数据来自 SceneData 构造函数，构造函数先于物理初始化执行。
- 秘宝之海主页、关卡、任务、奖池和守卫战入口，共 5 个 prefab 的 9 个背景节点使用 ann1 CG。将原有 Sprite、Texture2D 嵌入页面文件，以本地 PPtr 引用，避免额外外部依赖；采用默认 UI 材质且不拦截点击。逐页确认 Sprite 可解码为 1336×752。这是兼容 CG，不宣称恢复原官方背景绑定。
- 工具 tools/savemanager/client/patch_treasure_activity.py；资源和原生审计在其 build/treasure_activity 子目录。

## 服务端

ActivityRuntime 补齐当前开放塔防活动的 QueryActivityTower 与 ActivityTowerPassive 查询，并按查询处理，不附加整套玩家推送。未拥有的升级塔用客户端明确跳过的 ID 0 空条目表示，避免缺失 List 导致空引用，也不免费发放付费塔。秘宝之海使用 TowerController 和 SectionTable 的战斗配置，无 TowerRank 条目，因此被动查询按客户端明确允许的空列表应答；有 TowerRank 的全景裂隙按表权重选取并保存当期被动。

未在本轮实现旧式塔的局外购买、升级或返还协议。秘宝守卫战的局内塔由客户端 TowerDefenseModuleNeo 与既有配置处理。

## 交付与验证

- D:/demo/x2/逆向/打包/X2-Revival-Treasure-Local-signed.apk：10.0.2.2:18080。
- D:/demo/x2/逆向/打包/X2-Revival-Treasure-Remote-signed.apk：8.163.2.72:18080。
- 两份均 2,146,641,747 字节；正式发布证书 v1/v2/v3 验证通过。低于 2 GiB-1。
- 相对于 ActivityUI 本地版，仅 7 个资源文件和 libil2cpp.so 的内容变化；存档管理、classes5.dex、libunity.so 保留。本地与远程内容仅 GameConfig 不同。
- 6 项相关测试通过，涵盖守卫战查询、协议异常回滚、奖池交易、当期全部活动关卡进入/结算、活动初始化协议。
- 本地服务器 20:17:16 启动成功；活跃 phase14 数据库已备份为 runtime/before_activity_ui_followup_20261011_201715.sqlite3。活动仍为秘宝之海。
- 未安装 APK 或执行游戏内验收，交由用户安装本地版后手动检查。远程服务器未部署，远程 APK 需要匹配本轮服务端修复。

打包时 D 盘不足，清理两份已有签名发行版对应的旧 ActivityArt unsigned 构建缓存和本轮失败临时产物；发布 APK、源码、存档保留。后续 AllocatorFix 基线文件不再可用，远程包由已验证的 Treasure 本地签名包仅替换远程 GameConfig 后重签生成，无重复追加存档管理 DEX/动态库。
