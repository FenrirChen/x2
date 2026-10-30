# 镜域额外层的 4 周目轮换（2026-10-30）

## 现象
社团「镜域试炼」的额外层（2170037~2170052，界面上的第 4 周目那一组）开始，BOSS 进不去、
宝箱点了也没反应；玩家反馈「四周目箱子领不到」。本地私服与上游同源，两边都复现。

## 根因（三个问题叠在一起）
1. 服务端把 52 层当成一次性的线性进度：`mirror.clears` / `mirror.claimed` 永不重置。
   4 周一轮走完一轮之后，所有额外层都是「已通关 / 已领取」，`admission` 直接报
   `mirror boss already cleared`，`ClubReceiveReward` 报 `mirror reward not eligible`。
2. PR #77 为了修「换成猫后打不了」，把 2170037 以上的顺序门禁整个放开（只校验合法、
   未通关、次数）。它可以越过常驻 1~36 的缺口、提前打后面周目的层，服务端的记录和
   客户端算出来的 `cur` 错位，宝箱反而永远不亮。
3. NPC 跟打（`completed`）从全量 52 层表往后扫，会跨进下一个周目组，把未来几周的
   BOSS 提前打掉（伤害按 90%/45%/22.5% 递减，跨两三只也能杀死低层）。

## 客户端证据
- `ClubModule_Get5AMWeekIndex` = `floor((ServerTime - 18000) / 604800) + 1`，`ServerTime` 是
  服务端下发的 Unix 秒 → 每周切换点 = 北京周四 13:00（每天 13:00 刷新的那个点再 +7 天）。
- `ClubModule_GetClubActivityCurExtraLayerStart` 里 `start`（0 基）=
  `N + 4 * (weekIndex % 4)`，`N` = `GlobalParamString.NewGuildInstanceStartLayers - 1` = 36。
  换算成 1 基层号，四个周目的首层依次是 **37 / 41 / 45 / 49**。
- `ClubModule_GetClubActivityLayer` 从 Meta 里收集 `clubLayer_`（前缀、`VInt64 >= 1`、
  层号 = 后缀），过滤掉 `index < 36` 和「不在当周这 4 层」的记录，再求**从 0 起连续**的
  前缀；常驻层有缺口时 `cur` 就停在缺口上。
- `ClubActivityInfoView_RefreshReward` 的宝箱循环：`w24 = start + i`（i=0..3），
  `received = mReceivedLayer.Contains(StageID)`、`canReward = !received && w24 < cur`。
  所以**4 个宝箱全亮必须 `cur == start + 4`**，也就是常驻 1~36 全清 + 当周这 4 层按顺序
  清完；常驻层有任一缺口时，额外层宝箱永远不亮（客户端硬限制，不是服务端能绕过的）。

## 服务端改动（social.py）
- 新增模块常量 `MIRROR_BASE_LAYERS=36`、`MIRROR_ROUND_LAYERS=4`、`MIRROR_WEEK_SECONDS=604800`、
  `MIRROR_WEEK_SHIFT=18000`，以及 `mirror_week_index()` / `mirror_block_start()`。
- `mirror.round` 存的是**周目号**（`Get5AMWeekIndex`），不是首层号：只存首层号的话，
  玩家隔 4 周回来正好撞上同一组，进度永远等不到重置。
- `state()` 里调用 `mirror_sync_round()`（只在内存迁移，读接口仍然不写库；下一次真正
  写状态的请求会一起落盘）。
  - 老存档（没有 `round`）：常驻进度原样保留，额外层只留当周这组；其领取标记与通关记录一起保留，防止迁移后同一宝箱重复发奖。无法证明历史周目的记录不擅自判为未领取，下一次明确换周目才重置。
  - 换周目：额外层的 `clears` / `damage` / `sections` / `claimed` 全部作废，常驻 1~36 保留。
    4 周一轮会转回同一组，所以判断的是周目号而不是首层号。
- `metadata()` 只下发常驻 1~36 与当周 4 层的 `clubLayer_*` / `clubDamage_*`。客户端的
  `GetClubActivityLayer` 本来就会按层号过滤，但多发会让「已清层」看起来永不清零。
- `mirror_current()` 改成「先常驻 1~36 按顺序清，全清后才轮到当周 4 层」——和客户端的
  `cur` 完全一致。
- `admission()` 恢复顺序门禁：常驻层必须是当前层；额外层必须属于当周这 4 层且是当前层。
  周目感知之后 `current` 就是客户端的 `cur`，「换成猫后打不了」不会再出现，门禁可以恢复。
- `completed()` 的 NPC 跟打只沿「常驻 1~36 + 当周这 4 层」这条链往后走，不跨周目组；
  跨周目边界迟到的结算直接拒绝（不扣次数、不发奖励、不写血池）。

## 数据修复（club_catalog.json）
- `2070001.stageIds`：`[2070001, 2170001]` → `[2170001]`（多了一个 BossID）。
- `2070024.stageIds`：`[2170024, 1]` → `[2170024]`（`1` 是脏数据）。
- `2070024.winConsume`：`[1283204]` → `[1283204, 1]`。原值是「只有物品 ID 没有数量」，
  `len(consume) != 2` 会让服务端直接报 `mirror reward key unavailable`，这一层的 NPC
  帮杀宝箱永远领不到。

## 钥匙与「NPC 帮杀层领不到」
额外层宝箱的钥匙 `1283201~1283207` 只在社团商店（shopId 807）售卖，
`gift_contents.json` 里没有任何 gift 会发放它们。玩家亲自参与过的关卡免钥匙；
只有 NPC 帮杀（玩家没进那关）才需要精确扣一把钥匙。缺钥匙时拒绝领取是既有设计
（`test_npc_only_clear_requires_exact_key_and_keeps_atomic_failed_purchase`），
本次没有放开，只修了 2070024 的脏数据。

## 验证
- 新增 `tests/unit/test_club_mirror_rounds.py`（7 项）：周目切换点/四组循环、常驻优先与
  顺序门禁、换周目清空额外层、4 周后转回同一组仍能重打与重新领箱、NPC 跟打止于块边界、
  老存档迁移、跨周目迟到结算被拒。
- 既有 `test_club_mirror_rewards.py` / `test_club_mirror_assists.py` / `test_social.py` 全绿
  （合计 46 项，含新增）。未改 APK。

## 已知边界
玩家手里如果常驻 1~36 还有缺口，客户端的 `cur` 会停在缺口上，额外层宝箱依旧不亮——
必须先把 1~36 按顺序打完。这不是 bug，是客户端的硬限制。

## 本地审查补修（2026-10-30）

PR #93 aaea1eb已通过本地merge保留原作者提交。重新读取本机原始libil2cpp.so确认周目偏移18000、除数604800与余4分组；本机原始RVA是Get5AMWeekIndex=0x1585284、GetClubActivityCurExtraLayerStart=0x15644E8，与PR文字中的地址有差别。原始反汇编保存analysis/pr93_20261030/native_week_rotation.txt。

新增两项测试先在PR原实现复现失败，再补修：
1. 未带round的旧档，PR保留当前组clears/sections却清除claimed，会使已领奖宝箱再次获得资格。现迁移同时保留当前组已领标记；正式换周仍清除额外层进度。
2. 待结算run没有周目绑定，PR仅检查关卡是否属于当前组，四周后同组重现时旧战斗仍能写入新血池。新run保存round；旧未绑定run只有本账号battle_entries.created_at能证明属于本周时才允许结算。过期或无证据拒绝，不扣次数、不发奖励。已完成run继续幂等重放。

周目同步仅采样一次时间，避免切换瞬间week与block使用不同时间。存档格式不变，round保存在原社团JSON中，导入导出自然保留。

原PR遗漏更新test_rotating_extra_layer_admits_and_damages_its_own_boss：该旧测试允许未清常驻层直接进入任意额外层，与本次客户端顺序契约冲突。已改为四组参数化覆盖，要求常驻已通关后进入当前组首层；其余组不因改测试而放开。

补充旧档已领奖不重复、四周后旧run拒绝、旧run同账号入场时间举证/无证据/过期三组、24层NPC箱精确扣一把1283204钥匙，以及真实BattleService入场→结算→重放→领奖→防重→四周后重新开放闭环。最终76项回归全部通过（29.11秒），测试报告见analysis/pr93_20261030/review.json。未修改APK，未推送远程。
