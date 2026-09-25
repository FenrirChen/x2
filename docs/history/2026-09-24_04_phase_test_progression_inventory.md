---
Document-Type: Historical Report
Date: 2026-09-24
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# 魂器解锁与测试资源存档

2026-09-23，当前 MuMu 12、Revival v0.2、既有玩家 1／`revival`、活跃库 `runtime/phase14/player.sqlite3`。仅处理魂器请求与独立测试资源工具；Reference APK、主线与账号未重置。

## 魂器 loading 根因及请求链

用户手动点击“解锁”后，旧服务器日志于 20:08:56 首次记录 `message=143/unknown request=89`，没有响应。客户端约 8 秒后重连并重发 requestId 89。客户端 `dump.cs` 的 `ERequestTypes` 确认 143 为 `C2L_Artifact`、146 为 `L2C_Artifact`。定向日志在重连后捕获请求体 `080010eb0718002000`，即 `opt=0 (JO_LevelUP), HeroID=1003, JewelID=0, HoleIsID=0`。服务器此前缺消息注册、protobuf schema 和 handler，所以 loading 等不到回包。

客户端路径：`ArtifactModule.ArtifactLevelUP` 发 `C2L_Artifact`；`L2C_Artifact` 的字段为 `result/opt/HeroID/JewelID/HoleIsID`。`ArtifactModule.OnMsg` 检查 `result == E_Ok (10)` 后执行 `RefreshData`，再按 opt 更新对应 UI/事件。回包沿原 requestId，状态经 `L2C_HeroUpdate` 推送；同一事务还使用既有 `PlayerDataProto`、`L2C_ItemUpdate` 和任务推送路径。服务端按 `ArtifactFuse` 的职业 303、rank 0 行核对首次 `JO_LevelUP`：升级材料空、金币 0；没有额外消耗。其他魂器操作仍需独立核实，不能将本次首解锁视为完整升级／熔合验收。

首次服务实现曾写入 `HeroGodEquip(id=1503,level=1,star=0)`。客户端虽提示“解锁完成”，重进仍显示解锁；重复点击得到 code 13。定点反汇编 `ArtifactModule.RefreshData` 显示 `HeroGodEquip.star` 读入 `ArtifactModule.Star`，`HeroGodEquip.level` 读入 `ArtifactModule.Fuse`。因此本次 `JO_LevelUP` 后的兼容实例改为 `id=1503, level=0, star=1`，`godEquipAttr` 为已存在的空嵌套对象，`jewel` 无条目。动态属性没有官方生成证据，存档标记 `REVIVAL_COMPAT`。当前用户确认无需重登，魂器页已正常；退出再进和重新登录后的本次最终字段仍待单独验收。

存档更正前保留 `runtime/backups/before-artifact-stage-correction-20260923-202254.sqlite3`，更正仅匹配本轮误写的 `REVIVAL_COMPAT/id=1503/level=1/star=0`。更早的 `runtime/backups/before-artifact-20260923-201619.sqlite3` 保留首次操作前状态。SQLite 玩家 revision 18→19，角色等级、星级、主线、任务及战斗记录未改。服务端 handler、schema 与消息注册的代码有针对性测试；服务日志记录初次 `L2C_Artifact code=10`、`L2C_HeroUpdate` 及后续错误码，客户端最终状态已由用户当前页面确认。

## 测试资源工具

`tools/dev/seed_test_inventory.py` 独立于正常登录与账号创建逻辑；默认当前玩家 1、活跃库，支持 `--player`（ID 或账号）、`--dry-run`、`--mode ensure|add`，以及 `--preset currencies|hero|artifact|equipment|progression` 和额度参数。真正修改前用 SQLite backup API 在 `runtime/backups/` 建立不覆盖的时间戳备份，随后在事务中按 revision 更新。`ensure` 只补足目标额度，重复运行不无限增加；`add` 是明确的累计模式。运行摘要列出余额、材料类型、实例数量与备份路径。

货币走玩家快照字段，并由现有 `PlayerDataProto` 登录推送；可堆叠材料走 `inventory`，由正式 `L2C_ItemAll`／`L2C_ItemUpdate` 路径同步。ID 源于 `analysis/progression/material_links.json`、`skill_progression.json`、`weapon_progression.json` 与现有经济目录；明确排除 `E_Equip`。默认金币 10,000,000、光辉 100,000、神格经验 10,000,000、普通材料与碎片 999；材料如有 `PileCount` 则取更低的静态上限。`progression` preset 收集当前恢复范围内的全部成长材料；可用较窄 preset 控制背包测试范围。

兽主测试实例使用 `EquibBase` 真实 typeId、部位／套装和 `EquibAttribBD` 的确定性候选预设参数，标记 `TEST_COMPAT_INSTANCE`。具体从 400–405 六个套装各取六个部位、star 6；套装 406 取六个部位、star 5；总共 42 件。初始 level/exp 为 0，唯一实例 ID 由 SQLite 分配；同一 typeId/标记的实例不会重复创建。选择固定静态候选并复用于测试实例是兼容策略，并非官方随机掉落或副词条算法。来源目录为 `analysis/progression/equipment_seed_catalog.json`，可由 `tools/dev/export_equipment_seed_catalog.py` 从已索引的两张 Equib 表重建。

实例保存在独立 `equipment_instances` 表。正式登录 `L2C_Login.equipAll` 和 `C2L_EquipAll`→`L2C_EquipAll` 均通过 `HeroEquip/EquipParam` 原协议发出，未把兽主当普通 Item count。装备及强化 handler 已接入，UI 可见性和即时刷新由实机分别验收。

实际运行 `--preset progression --mode ensure` 后，玩家 1 的金币 12,340→10,000,000、光辉 90→100,000、神格经验 1,240→10,000,000，110 类可堆叠成长材料补到目标值；备份 `runtime/backups/before-test-inventory-20260923-202521.sqlite3`。随后两次 `--preset equipment --mode ensure` 分别创建 36 件六阶及 6 件五阶实例，备份 `runtime/backups/before-test-inventory-20260923-202747.sqlite3`、`runtime/backups/before-test-inventory-20260923-203110.sqlite3`。第二次 `progression ensure` 已实测 0 材料变更、无新备份。账号等级和主线不会被该工具修改；用户可能同时进行养成测试，因此动态等级／余额须读当前 SQLite，不以本段历史数值回写。

## 当前验收状态

| 项目 | 状态 |
|---|---|
| 首个魂器请求与无回包根因 | 实机日志确认 |
| 首次响应 code=10、HeroUpdate、SQLite 持久化 | 服务日志／数据库确认 |
| 魂器当前页面显示正常 | 用户确认，无需重登 |
| 最终字段下退出重进、重新登录 | 已多次重连并继续养成操作；角色状态由登录及更新消息同步 |
| 测试资源脚本 dry-run、重复运行 | 隔离测试通过；活跃库重复确保无变更 |
| 测试资源实际发放 | 金币、光辉、神格经验、兽魂及 110 类材料已入库并备份 |
| 兽主实例 | 42 件已入库，登录／EquipAll 同步；用户确认兽主已无问题 |
| 客户端背包、装备、强化 | 用户确认兽主已无问题；强化事件具体随机权重仍为兼容策略 |

## 人工反馈后的定点补修

用户在首次资源发放后反馈：神格碎片合成角色失败、兽主佩戴失败、缺少兽魂、绯红之刃继续升级失败。服务日志给出 `C2L_HeroOpt`（请求角色 1008/1009，旧 handler 仅接受已拥有的 1003）、未知 ID 118（`C2L_DoEquip`）及 `C2L_Artifact opt=0` code 13。旧 `Artifact` handler 只允许首次解锁，因此后续阶段被拒。

- **角色合成**：`HeroOptCode.OPT_UNLOCK=0`。从 `PlayerAttrib` 定点导出 39 个开放英雄的 `ChipPropID/ExchangeChip/DefaultStage/Level/WeapenId`，并从 `SkillBase` 取初始五个普通技能 ID。`analysis/progression/hero_unlock_catalog.json` 保存证据；服务端原子扣专属碎片并建立新 `HeroData`，推 `HeroUpdate/ItemUpdate`。初始运行态结构标记 `REVIVAL_COMPAT`；未把静态原型冒称官方服务端实例生成规则。
- **兽主佩戴**：按客户端 `C2L_DoEquip` 118、`L2C_DoEquip` 120 和 `C2L_DoUnEquip` 540、`L2C_DoUnEquip` 541 实现测试实例的装备／卸下。部位由已导出的 `EquibBase` 测试目录给出，`HeroData.equips` 存位置→唯一实例 ID；跨角色佩戴时原位置解除，替换同部位装备。成功后推 `L2C_HeroUpdate` 与 `L2C_EquipUpdate` 536，登录及 EquipAll 查询继续从存档同步。只接受普通装备类型和当前测试实例。
- **兽魂**：经济静态证据 `ItemID=1237906`、`E_Currency`、`EffData=906`，客户端 `CurrencyType.E_EquibExp=6`；它对应 `BaseInfoProto.EquipExp` protobuf 字段 7，不是普通可堆叠 Item。`equipment/progression` preset 现确保 `equip_exp` 10,000,000；本次补发备份 `runtime/backups/before-test-inventory-20260923-204505.sqlite3`。
- **兽主强化初版**：按 `EquibExp` 的 0→1、1→2 两行逐级消耗兽魂 30/50 与金币 500/800，更新独立实例 level。其后用户反馈 +3 属性未变、+4 失败，见下方纠正。
- **魂器后续升级初版**：误将 `JO_LevelUP` 直接增加 `HeroGodEquip.star`，导致每点一次“升级”就升星；该错误已按客户端按钮分支纠正，见下方。

补修后本地回归 **166 passed**。`runtime/phase20/growth-followup.err.log` 是本次部署的定向日志；以上四项的最终客户端结果等用户本次人工复测，不用隔离测试代替实机验收。

初次复测日志出现两次新角色合成 `HeroOpt` code 10、多次 `DoEquip` code 10；数据库现有角色 1003/1004/1008。用户随后据实际画面指出位置错位、魂器升级变升星、+3 属性未提升、+4 报失败及强化窗未即时显示等级，这些反馈优先于回包 code 10。

## 实机纠错与当前部署

- `EquibBase.EquibPart` 为 1–6，客户端 `HeroData.equips` 的位置键为 0–5；原实现直接发送 1–6，使部位 4 显示到 5，部位 6 不显示。服务端现发送 `part-1`。迁移脚本仅对当前测试账号已经写入的 7 个绑定逐个减 1，保留实例 ID 与角色归属。
- `ArtifactUpgradeTab.BtnEventTiShen` 的原生分支在 `ArtifactModule.Fuse < 100` 时调用 `ArtifactLevelUP` (`opt=0`)，达到 100 才调用 `ArtifactFuse` (`opt=1`)。`RefreshData` 从 `HeroGodEquip.level` 读进度、从 `star` 读星级。`ArtifactFuse.FuseValue` 已补进审计及运行目录：rank 1 每次增加 10 点进度。所有 4 种职业、39 个开放角色的专属魂器 ID/职业均从 `PlayerAttrib` 导出；已拥有角色可按其职业解锁。满 100 后才按对应职业／rank 的熔合材料和金币升星、进度归零。

2026-09-24 后续修正：`ArtifactOpt.JO_Beset=2` 现按客户端 `HoleIsID` 原值作为 `HeroGodEquip.jewel` 的 `Key`，绮石物品 ID 作为 `Value`；不对孔位加减偏移。镶嵌验证 115 个客户端 `JewelBase` 绮石 ID 和玩家库存，更换与卸下返还原石，同一请求重复提交由收据保护。魂器进度与星级在镶嵌时保持不变。相邻孔位 5、6 的编码及返还已由隔离存档测试覆盖；实际客户端显示仍需现场确认。
- 旧实现使绯红之刃由 1 星误到 5 星，实机日志有 4 次成功升级请求。定点迁移把它更正为 **1 星、40 点进度**，并按 4 次 rank 1 正确成本与旧 rank 1–4 错误成本的差额调整相应材料及金币；没有修改角色星级。操作前备份 `runtime/backups/before-phase20-state-repair-20260923-211800-7879e3.sqlite3`。`repair_history` 保证迁移重跑不重复扣补，已实测第二次无变更。
- `EquibExp` 在等级 3、6、9、12、15 标事件。达到这些等级时，从当前装备已存在的副属性位置 2–6 随机选一个，并以 `EquibAttrib/AttribSRC=3` 对应品质、属性的值域增加一次；结果存入实例 `EquipParam`，事件记入 `equipment_enhancements`。这是有静态值域依据的 **REVIVAL_COMPAT 随机策略**，不是已证实的原服权重算法。迁移时给两件已到 +3 的测试兽主各补了一次，不重复扣升级成本。+3→+4 已开放并按 `EquibExp` 继续逐级扣费。
- 强化窗口收到 `L2C_EquipStrengthen` 成功后立即从背包记录刷新；原服务端先回成功再推装备变更，导致窗口读旧等级。现在对该请求先推发生变化的单件 `L2C_EquipUpdate` 和余额，再回原 requestId 的 `L2C_EquipStrengthen`。装备实例的 `level/param` 在同一数据库事务中持久化。

此阶段本地完整回归 167 passed。随后实机截屏看见魂器进度条，但在满进度后又出现升级请求：客户端收到成功回包时还未收到新角色状态，界面仍读旧进度。因此魂器操作改为先推 `L2C_HeroUpdate`，再沿原 requestId 回 `L2C_Artifact`；之后客户端实际发出 `opt=1` 熔合请求，并得到成功回包。

## 最终魂器门槛纠错与验收

用户再次实测发现部分角色解锁后不能升级，部分角色到 2 星不能继续升级。失败时实机请求分别来自低角色阶段的 1 星／2 星魂器；原服务端在 `opt=0` 普通升级前检查了 `ArtifactFuse.HeroStage`。客户端将该阶段条件用于满 100 进度后的升星熔合，普通升级只核对当前职业／rank 的材料、金币与进度上限。现已将角色阶段门槛移至 `opt=1` 分支。服务端同时开放已恢复目录内其他角色使用专属碎片的神格升星，以便满足后续熔合门槛。

21:45 前后的实机日志 `runtime/phase20/artifact-stage-fix.err.log` 记录原本卡住的角色继续多次 `opt=0`，回包 code 10，进度实际写入存档。用户最终反馈“没问题”，兽主和这两类魂器普通升级卡点均通过当前实机复测。满进度的熔合仍按客户端静态表的角色阶段要求执行；例如角色 1008 的魂器已到 3 星／100 进度，但角色阶段 5 低于下一熔合要求 8，`opt=1` 返回 code 13。这是当前明确保留的进阶条件，提升神格阶段后可再测试对应熔合。不要把普通升级通过理解为所有星级熔合均已验收。

最终本地全量回归 **168 passed**。目前本轮最大未恢复边界为原服装备属性随机权重、魂器动态属性精确算法及更高阶段的完整实机熔合验证；现用静态表约束和 `REVIVAL_COMPAT` 标记保留可重复测试状态。
