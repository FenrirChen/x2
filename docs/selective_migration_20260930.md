# X2 Revival 2026-09-30 选择性移植实施与审计

工作区：`D:\demo\x2\x2_revive_workspace`，分支 `main`。
仅本地 Git 提交；未 push，未重启正式服务端。Active DB 未执行迁移探测。

## Implemented

| 项目 | 实施结果 |
| --- | --- |
| A-03 联结 | 保留 main Favor 系统；从 main 官方 FavorabilityFetters 的完整十阶数组取共同条件表，验证位置、拥有状态、好感、星级、等级和金币；同一事务扣款与快照更新；HeroUpdate 与余额推送。拒绝不扣款。 |
| A-04 任务 repair | 同周期内补建新满足 AcceptLevel 的任务；负进度归零；从该周期永久 grant receipt 恢复已领奖状态；已领奖进度至少达到目标；不降低更高进度；不改变原有周期切换和历史归档。 |
| A-06 推荐页 | 使用当前 GiftPackageService.listing 可购买条目，配合已证实的 JumpID、RecommendTag/HotAreaParam；HTTP GET 白名单 PNG；使用现有 DeploymentEndpoints。没有每日推荐轮换、午夜截止或礼包运营推送。 |
| A-08 手动刷新 | 随机池逐次改变选择；静态槽位整体轮换商品、数量、价格及货币，兑换货币槽位保持稳定；ShopConfig 刷新费用梯度；每日刷新计数与请求 receipt 持久化；每日槽位购买上限仍为一次，刷新不抹除已购买状态。809 保持不可手动刷新。 |
| B-01 DP | 官方 260 条任务目录、12 个章节任务分组和50个结构化宝箱内容已接入；新增 chapter_signals 与 chapter_objectives；替换旧简化 DP 聚合；保留已有永久宝箱领取账本；见后述事件缺口，不能宣称全部260条已可实际完成。 |
| B-02 264 recorder | 原始 body、解析数据、items、npc/currency/heros/killMonster/antiCheat 声明及 player/run/context 持久化；按 player/run/body digest 去重。记录失败不改变原有正式266响应。没有奖励逻辑。 |
| B-04 battleSkinId | 从 main appearance_wear.type=1 读取当前穿戴皮肤，下发 FightHero field10；保留 heroGodEquip、monsterInitLevel、expertMode、difficulty 和现有战斗 builder。 |
| B-17 工具 | PlayerStore.backup_to 与独立 tools/sqlite_backup.py；独立只读 tools/inspect_drop_reports.py；独立横幅资产构建工具 tools/dev/build_recommendation_assets.py。不接入 GM 或新启动体系。 |
| A-17 限定外观 | 全 canonical 155头像、75头像框/勋章、9场景开放。头像框在 ItemAll/ItemUpdate 读模型中提供，真实 inventory 不批量灌入；IconInfo.OrnamentID 与 Account 选框持久化；头像/场景继续保存当前选择。皮肤、语音仍按 main 的拥有/养成条件。 |

### 推荐素材覆盖与 fallback

本轮仅移植当前选定礼包中已证实跳转的四项：2700000、2700001、2700017、2700033。
其中免费每日类型不参加推荐，尚未开放或已购买条目也不参加推荐；Lv.80 礼包沿用原开放条件。
2700000 使用月卡原始美术 fallback，记录在 recommendations.json.imageRule/donor；其余三个为原始对应图片。
没有为缺少 JumpID 的礼包猜造跳转；因此当前账号可能只显示一个可购买的月卡推荐。这仍是一条完整横幅/跳转/HTTP链路。

## DP Audit

### 260 tasks / 12 chapters

260 个 taskId 全局唯一；任务分组如下：

| chapterId | tasks | DP总分 |
| --- | ---: | ---: |
| 2010100 | 27 | 100 |
| 2010200 | 25 | 100 |
| 2010300 | 26 | 100 |
| 2010400 | 26 | 100 |
| 2010500 | 23 | 100 |
| 2010600 | 24 | 100 |
| 2010700 | 26 | 100 |
| 2010800 | 24 | 100 |
| 2010900 | 29 | 100 |
| 2011000 | 1 | 2 |
| 2011100 | 28 | 100 |
| 2011200 | 1 | 2 |

260 条均有完整客户端条件。正确解码后恢复651113/condition600091：击败5040一次，奖励2DP。
四条 E_KillMonsterInSan（650918、650919、651117、651118）的状态分段击杀证据尚未恢复。
普通击杀不能被误算成某个理智/疯狂状态的击杀，故这四项没有猜测性完成逻辑。
2011200 存在于任务目录，但现有 ChapterInfo 使用2019900；没有擅自映射这两个不同章节ID。

### 50 boxes

50 个 supported 宝箱（1203801–1203850）依据 Item.Used 引用 Gift.GiftValue/Num 发放，普通奖励及装备套装映射均逐项测试。
六件兽主奖励使用当前 main EquipmentInstanceFactory/materialize_instances，保持原强化与副属性规则。
未领取时直接发放宝箱完整内容，不再仅给不可打开的容器道具。
宝石由 DP source 专用合法 destination 接入，不扩大其他来源奖励的权限。
1203841 文本“卡恩斯x10”与执行配置不同：Gift730950实际发1201013碎片x10、1251090魂石源质x10、金币20000。以结构化客户端数据为准，移除此前角色卡及重复转换分支。
1203846–1203850虽无Language描述，Item.Used引用731250–731255保留完整奖励，现已支持。
兽主六部件ID来自GiftValue；星级由GiftShow -> Item.NameID -> Language的“4★套装”确定，包括缺描述的1203847。

### event mapping

| 条件 | main 实际来源 |
| --- | --- |
| E_KillMonster | 成功战斗 receipt 后 C2L_FightKillInfo，按真实unitId；run/hero/unit累计最大值。原有每日击杀处理保持原样。 |
| E_BeatSection | economy_clears；已有有效通关可恢复。 |
| E_ShopBuyItem / E_ShopSpendMoney | 已成功的大厅购买receipt，以及绑定当前未结束run的 BattleShopService 购买；使用itemId和货币枚举，棱镜903。 |
| E_GetItemID | 当前inventory及明确的战斗携出/报告拾取证据；装备按实际部件ID。 |
| E_NPCInteraction | 已校验当前entry的264 npcData(id,count)，按run累计最大值。 |
| E_GetMoneyPer | 264 currency.field3 本局获得棱镜，field4=903；取单局最大，忽略带入金额。 |
| E_GetItemQuality / Per | 当前结算真正生成的兽主实例星级；历史 reward_settlement_audit 的 EQUIP_INSTANCE 证据可迁移；神迹只计算 dropItem 中实际出现在 relicList 的条目。按客户端完整品质列表匹配，-1为任意；单值5只计算五星，[5,6]计算五星及以上。Per限制同一run。 |
| E_KillMonsterInSan | 框架支持独立状态信号，但当前没有足够证据接线，保持未完成。 |

### idempotency / claim / relog

- run/subject/scope 使用最大累计值；100→50→120不会累计成270。请求ID变化与重连不会重加同一个计数。
- 264 recorder 按原始body摘要去重；DP信号按run维度去重，两者均不生成道具。
- 成功结算在当前 battle receipt 事务内记录装备与任务状态；receipt重放不再次结算。
- 宝箱检查task_boxes及economy_grants，事务内完成全部内容发放、实例生成及领取记录。
- 发奖后推送TreasureBoxUpdate；装备/角色奖励补EquipUpdate/HeroUpdate。再次领取拒绝。
- chapter_objectives、chapter_signals、永久领取记录随数据库保存；重新登录/服务重建读取同一状态。
- 50项内容发放测试、实际成功结算/击杀重发/264重发测试、领取重复测试和重建服务恢复测试通过。

### 与旧简化 chapter DP 的迁移

旧的“剧情通关数＋月相等级之和”不再计算，也不与官方任务相加。
旧永久宝箱领取保留；若task_boxes缺行但economy_grants有永久记录，补回领取标记，避免再发奖。
有效通关、当前背包及已存在的兽主结算审计可以还原；没有单位明细的历史击杀不猜造。
chapter_dp_floors 原值归档到chapter_dp_migrations.legacy_floors，不再计入DP。
因此原测试账号“跳过第二章”的人工10DP地板不再作用，下一章节门槛可能重新要求真实任务DP。
此前旧存档副本探测使用了仅第一档计分（第一章6/70、第二章4/64），该分母已被客户端完整多档数据纠正为100。正式Active DB未执行该探测。
保留原始在线备份：runtime/phase14/backups/pristine_before_selective_20260930.sqlite3。

## Explicitly NOT Implemented

B-03：NOT IMPLEMENTED；没有导入trial_units，没有修改现有试玩分支。

排除项：A-05、A-07、A-09、A-10/A-11/B-09、A-12/B-14、A-13/B-15、A-15/A-16/B-10、A-19/B-16、B-06、B-08、B-07全量外观兼容，以及A-17限定三类之外的全解锁。
没有替换 economy.py/battle.py/login.py/favor.py，没有导入第三方掉落预算空响应、兽主工厂、交易depth、卡池或启动体系。

## Tests

- Focused：56项通过，覆盖联结、周期repair、DP、商店、外观、战斗、264与备份。
- DP：50个宝箱逐项完整奖励/实例验证；260任务唯一性/12分组；真实战斗receipt与重复kill/report；永久claim与relog；实例更新推送；客户端碎片配置取代文字猜测。
- Full：完整测试尝试发现7项依赖缺失的历史分析文件（language.json/dropprop.json等）；这些文件在本机不存在，未伪造或替换夹具。排除这7项后，其余完整测试最终394项通过。
- 在线备份：SQLite backup API复制Active DB，完整性ok；正式数据未迁移或批量修正。
- 客户端复核修正后的定向回归：DP、economy及battle observer测试33项通过；覆盖多档计分/替代ID/精确星级/100点领取/50个宝箱/重复领取与重建恢复。

## Conflicts / Remaining Unknowns

1. 已确认20/40/60/80/100为点数。完整多档任务在第1–9及11章配置总计100，第1–8章消除此前80/100不可达到的问题；第9、11章仍各有6点状态击杀未接线，实际来源上限94。第10及12章客户端仅有一条2DP占位任务，保留其真实数据。
2. 四条状态击杀仍缺已验证接入的事件源。客户端C2L_FightKillInfo.chapterTaskEvent提供候选来源，尚未接线验证，不用普通击杀填充。
3. 2011200/2019900目录ID不同，保留客户端真实ID。
4. 宝箱奖励已采用Gift结构化配置，描述与图片只供审查参考。
5. 推荐页仅使用已证实的当前礼包JumpID；未覆盖缺JumpID的其他礼包。
6. 7项历史分析工具测试缺外部源文件；正常业务链路测试可运行。
7. 正式服务未重启；本轮代码尚未部署到正在运行的进程，亦未push远程。
