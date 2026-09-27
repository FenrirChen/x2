# 2026-09-27 外部修复包审计与正式合并

## 最终合并结果（以下合并前审计保留为历史快照）

- 基线修复前：274 passed / 1 failed；`LoginService.server_config` 在未注入 economy 的隔离测试中解引用 `None`。修复后 275 passed。独立提交 `2932313`；用户主动删除的过时装备方案单独提交 `c8b8859`。
- 分支：`integrate/external-repairs-0925-0926`。未覆盖外部包整文件；未导入旧 economy、battle、equipment、login 或测试存档。最终全量测试见下方验收记录。
- 最终验收：`.venv/Scripts/python.exe -m pytest -q` → **282 passed in 58.14s**。本地服务已用最终代码重启，18080/29000/29001 三端口可连接；客户端实测仍待用户完成。

### Collection

来源：B 的 query/claim 协议形状和一次领取账本思路。官方依据：当前 canonical `Collection` 26 行及对应 `Gift` 26 行，构建脚本 `tools/dev/export_collection_catalog.py` 保存源表哈希。外部候选缺失的 1021/1030 条件已由 canonical 自动恢复。当前 `CollectionService` 以实际 `state==2` 英雄验证完整集合，用当前 `EconomyService.gifts` 与 `_grant` 同事务写领取账本，重复领取拒绝，查询和重登保留已领 ID。25 个 Gift 可由当前 RewardGrant 解析；133103 的奖励物 1260015 属尚未实现的 E_Medal 目标，整单拒绝且不标记已领。测试：`tests/unit/test_collection.py`。提交：`cbe6f4d`。状态：**PARTIAL（25/26 可领取），待客户端实测**。

### Affection

来源：A/B 的消息 ID、字段及客户端消费路径；数据来自当前 canonical `FavorabilityHero/Level/Fetters/Files/Dairy` 和 `Item`，`tools/dev/export_favor_catalog.py` 保存源哈希。状态存在 `players.snapshot.heroes` 的 favor、档案、联结字段，登录与 HeroAll 重建 FavorMap、archives、fetters。档案/手账可查询，满足官方等级条件的档案可解锁。

59 种 `Item.FunctionEff=E_AddFavorability` 且可在外部使用的礼物已识别。3 种单值 `EffData=[5]` 能按静态值在一次事务里扣道具并加好感；其余双值 `[10,15]` / `[35,50]` 缺英雄偏好选择规则，拒绝且不扣物。触摸增量/次数、联结升级完整条件与突破服务端规则未知，拒绝未知变更。**未采纳**固定 +10、3 次/日、登录自动 10 级、免费突破、跨事务送礼。测试：`tests/unit/test_favor.py`。提交：`3e71835`。状态：**PARTIAL，官方可证部分运行，待客户端实测**。

测试存档：在备份 `runtime/backups/pre-favor-test-gifts-20260927-105018.sqlite3` 后，仅对 `runtime/phase14/player.sqlite3` 的账号 `revival` / player 1 执行一次目标数 100 的定向补齐。59 种均由 0 补到 100；报告 `analysis/external_merge/favor_test_gifts_seed.json`。工具 `tools/dev/seed_favor_test_gifts.py` 用 `MAX(old,target)` 思路保证重复运行不无限叠加；测试 `tests/unit/test_favor_seed.py`。实际 SQLite 不提交。提交：`e8b0198`；送礼次数持久化补丁 `89c7700`。

### Shop

来源：B 的 145 格目录比 A 的 76 格完整，B 的 809 商品映射与当前直接证据冲突，故只导出非 809 的 130 格候选；当前 809 的 15 格保留。130 格中 116 格由当前 `_grant` 可安全发放并列出，14 格目标未支持而隐藏。官方依据：协议、ShopConfig、ShopGoodsGroup；B 的 Item/Num、部分价格、限购次数属于 **REVIVAL_COMPATIBILITY / USER_DECISION**，见 `docs/decisions/compatibility/shop_external_catalog.md`。当前 `ShopService` 支持货币验证、扣款、限购周期计数、回执幂等、当前 RewardGrant、任务事件及重登。804 兽主实例池、刷新池和不支持的奖励目标仍待后续。测试：`tests/unit/test_shop.py`。提交：`90168c7`。状态：**PARTIAL / REVIVAL_COMPATIBILITY，待客户端实测**。

### 其他外部代码

TreasureBox、Appearance、Voice、Account profile 等仅保留下方审计结论，未合并。所有贡献者旧版经济/战斗/装备/登录整文件代码均拒绝覆盖当前系统。

## 当前基线与安全门

- 正式仓库 HEAD：`4d0dd95`。全量 `pytest -q` 基线：274 passed、1 failed；失败是 `LoginService.server_config` 在简化测试未注入 `economy` 时读取 `None.POWER_RECOVER_SECONDS`。
- 已有未提交删除：`docs/equipment_instance_server_fix_plan.md`。按本轮用户给出的安全策略，代码合并已暂停，等待确认该删除的归属。未重置、未覆盖、未触碰活跃 SQLite。
- 两份包是各自完整旧版服务端快照，不是可直接应用的 patch。A：114 文件；B：121 文件。文件级哈希和映射见 `analysis/external_merge/package_{a,b}_manifest.json`，差异见相应 `package_{a,b}_diff_summary.md`。
- 两包都没有随附测试文件；其文档所述测试存在于协助者原工作树，不能当作这次交付的可运行测试。

## Shop

来源：A 的 `data/shop_goods.json` / `player/economy.py`；B 在此基础上扩大商品目录。当前正式项目已有 `player/shop.py` 的 809 店、15 条由 `Item.QuickBuyID` 反查的映射与独立事务。

- **官方证据**：`ShopConfig` / `ShopGoodsGroup` 确认 GoodsID、分组、静态默认价格、币种和限购类别；客户端 `L2C_Goods` 与购物请求确认通信形状。当前知识库明确多数 GoodsID→ItemID/Num 是缺失的服务端数据。
- **协助者规则**：A 76 格中 60 格标 `pairing`；B 145 格中 66 格标 `reconstructed`、62 格标 `catalog`、17 格标 `observed`。B 的 17 格价格和币种与客户端静态默认值均不同，包内没有可独立核验的原始服务端回包。B 的 809 店物品映射与当前 15 条直接 QuickBuyID 线索冲突。
- **初步决策**：保留当前 809 实现；其他目录及定价先 **DEFER**。只有拿到商品内容和数量的原始样本，或经用户明确接受的兼容目录决策后，才可扩店。外部旧 `_grant`、checkout、装备逻辑 **REJECT** 整文件移植。
- **状态**：Shop 仍为 **PARTIAL**；未新增测试或业务代码。

## Affection / 好感度

来源：A、B 的 `player/favor.py`、`messages/favor.py`；B 另带 `data/favor_catalog.json` 与较完整的档案/手账路径。

- **官方证据**：客户端协议有 `AddFavor` 274/277、联结 498/499、档案 500–503、突破 651/652、手账 657/658；`FavorabilityHero`、`FavorabilityLevel`、`FavorabilityFetters`、`FavorabilityFiles`、`FavorabilityDairy` 等官方表提供静态结构。
- **协助者规则**：固定每次 +10、每英雄每日 3 次触摸、登录把所有英雄抬升到好感 10 级，均不能归入官方规则。B 的送礼扣费和加好感跨两个事务，存在部分成功风险；非送礼交互还需补英雄归属验证。
- **初步决策**：协议形状、状态表设计和真实静态行可 **ADAPT**；固定增益、自动升到 10 级及无消耗突破 **REJECT/DEFER**。若采纳可玩性规则，须先在 `docs/decisions/compatibility/` 显式登记。
- **状态**：当前正式项目未实现该子系统；仍 **MISSING**，待安全门解除后移植。

## Collection / 图鉴

来源：仅 B 的 `data/collection_catalog.json`、`player/economy.py` 和协议增量。当前正式项目已有 `QueryCollectionAward` 空态查询，但没有领取实现。

- **官方证据**：`Collection` 静态表有 26 个奖励行和 GiftGroup；协议 `QueryCollectionAward` 586/587、`GetCollectionAward` 588/589。可借鉴 B 的已领取账本和重复领取防护。
- **数据冲突**：B 的 133101 条件少英雄 1021，133204 少英雄 1030；当前 canonical 全表有完整条件。B 的 GiftGroup 值与官方表一致，但当前经济目录缺 785011 等图鉴 Gift，直接复制 B 的领取函数仍会发奖失败。
- **初步决策**：**ADAPT**。以当前官方 `Collection` / `Gift` 全表重新生成目标目录，使用当前 RewardGrant、事务、玩家英雄 `state==2` 的归属判断和幂等领取；不默认解锁所有条目。
- **状态**：查询 STUB、领取 MISSING；尚未改业务代码。

## 其他领域与当前主项目保护

- B 的活跃宝箱 0 基索引和 `TreasureBoxUpdate` 是有价值的候选，但原始抓包未随包提供；先按客户端 send point 复核。状态 **PARTIAL/STUB**。
- A/B 的外观与配音全解锁属于兼容策略，不得写成官方恢复；账号资料和推送形状可独立审计。状态 **DEFER**。
- A/B 旧 `economy.py`、`battle.py`、`equipment.py`、`login.py` 不得覆盖当前 `RuntimeDropResolver`、`ReportCurrencyResolver`、264/266、分级预算、HeroEquip 工厂、结算与收据、生日及体力恢复。
- 旧存档 `save/demo.sqlite3`、账户配置、日志、启动器、APK/二进制和协助者知识文档均不进入正式项目。

## 后续合并门槛

1. 确认未提交文档删除的归属并使合并工作与用户现有修改隔离。
2. 将基线登录配置测试失败作为独立小修复处理并复测。
3. 分域移植、逐项证据分级和补充 Shop/Affection/Collection 的请求、事务、重登、重复请求测试。
4. 最终全量 `pytest`、覆盖目录和兼容决策同步后再提交分域 commits。
