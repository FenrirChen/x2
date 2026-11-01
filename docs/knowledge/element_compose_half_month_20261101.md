# 元素之章「可合成次数」按半月刷新，周刷新只重置周光（2026-11-01）

延续 `element_compose_history_20261017.md` 的记录。那一版把 `FormulaComposeAll`
做成了终身累计，于是配方页的「可合成次数」在第一次光能本刷新之后就永远是 0
（截图：`配方·铜星尘 (0/11)`），光能本自己却刷新了。

## 结论

- 配方页「可合成次数」的口径是 **半个月**，不是每周，也不是终身。
- 每周刷新的只有每周光能奖励（`WeeklyDungeon.EndlessWeekVowLimit` 880 的周光）。
- `Weekly.ElementExpAll`（元素经验）保持终身累计，跨半月不清。

## 周期取证

### 客户端问答表（决定性）

`table_json/AnswerConfig.json` 第 `281048` 条：

- `QuestionName 2810482`：「【乌洛波罗斯】的光能奖励，会按下哪个周期重置？」
- `AnswerName`：`[2810483 周, 2810484 15日, 2810485 月]`
- `RightAnswer = 1` → 「15 日」

即官方口径是 15 日一档，配合日历就是「1 日..15 日 / 16 日..月末」两个半月块，
切点和其它账号重置一样是北京 00:00。

### 客户端代码

`libil2cpp.so`（`work/_syms.json` 符号表）：

- `ElementComposeModule_MaxComposeNum` =
  `min(ComposeRoundLimit, ComposeNumLimit - (allComposeTime - singleComposeTime))`，
  `allComposeTime` 来自 `Weekly.FormulaComposeAll`，`singleComposeTime` 来自本局
  `FightDataProfile` 的次数；周期完全由服务端决定，客户端不参与。
- `ElementComposeModule_InitData` 只做减法，不做任何按周/按月的归零，所以旧实现
  （终身累计）没有任何渠道恢复次数。

### 服务端现状

- `endless.ensure_week` / `week_start`：`week_start` 为北京周一 00:00，
  `ensure_week` 跨周只把 `state['light']`（`activity_state`，`PERIOD=-38`，
  `NAMESPACE='endless-week'`）归零，周光上限 880 + `EndlessWeekMaxVowOfStone`。
- `element_compose.cumulative_values`：原实现按 `battle_element_compose` 全表求和，
  没有时间窗，因此永不刷新。

## 实现

- `player/server_clock.py`：新增 `half_month_start(now)`，返回 `now` 所在半月块的
  Unix 起点（北京 1 日 / 16 日 00:00）。
- `player/element_compose.py`：
  - `cumulative_values(store, player_id, now=None)` 拆成 lifetime 与 period 两个查询：
    `FormulaComposeAll` 用 period（`battle_element_compose JOIN economy_runs
    JOIN battle_entries`，条件 `battle_entries.created_at >= half_month_start(now)`），
    `ElementExpAll` 仍用 lifetime。
  - 用「开局时间」判定归属：只要这一局在本半月内开局并结算，即使它所在的那一周
    已经翻篇，次数仍然计入（正好对应「周刷新不清合成次数」）。
  - `compose()` 的 `numLimit` 校验改成 `used + count > numLimit` 才拒绝。原生
    `MaxComposeNum` 已经把本局次数算在 `allComposeTime` 里，旧实现再减一次本局
    计数会把上限放宽到 `numLimit + 本局次数`。这里的测试期望因此从 11 收紧到 10。
  - `COMPOSE_LIMIT_NOTE` 把上面的周期证据写在代码里，避免以后又被改回「终身」或
    「每周」。
- `player/endless.py`：
  - `CLIENT_WEEK_SECONDS=604800`、`CLIENT_WEEK_SHIFT=18000`、`week_number(now)`。
  - `weekly_values(store, player, now)` 把 `now` 传给 `cumulative_values`，保证推送
    给客户端的 `Weekly` 与限次校验用同一个时间基准。
  - `L2C_CheckFightProfile` 的 `currentWeek` 由写死 `272` 改为
    `week_number(self.economy.clock())`。

## currentWeek 为什么必须算

`ChapterModule_OnConfirmSave`（0x16C5B10）：

- `+0xa8 = currentWeek`（`L2C_CheckFightProfile` proto 字段 7）
- `+0xc0 = currentWeek*604800 + 18000`

`EndlessInfo_RefreshPage`（0x1C270C0）把 `+0xc0` 当作「本周结束」时刻，与
`ServerTime_GetServerTime`（Unix 秒）相减显示倒计时。写死 272 时
`+0xc0 = 164,523,600`（1975 年），倒计时恒为 0 且跨周永不变化——这就是「周本没更新」
的页面表现。周光 / 断点本身是按周清掉的，缺的只是这个序号。

`18000` 是 `ServerTime_GetRefreshTime` 里的 05:00 偏移（纯算术，不带时区），而
Unix 纪元是周四，所以客户端能表达的周界只能是「周四 05:00 UTC」，也就是北京时间
周四 13:00。这与本服 `week_start`（北京周一 00:00）差 3 天 13 小时，因此页面倒计时
的相位会有偏差。本补丁不改 `week_start`（会破坏现有周光存档口径），只保证序号随
时间递增、倒计时不再恒为 0。

## 验证

```
python -m pytest tests/unit/test_element_history.py tests/unit/test_endless_week.py \
    tests/unit/test_socket_compose_endless.py -q     # 14 passed
```

新增/调整的用例：

- `test_half_month_numlimit_survives_weekly_refresh_and_resets_on_the_16th`：
  上一半月的 12 次不计入本半月；本半月内连合 12 次成功、第 13 次拒绝；跨周刷新后
  （12-15）`EndlessWeekVowOfStone` 归零但配方次数仍为 12；跨 16 日后次数归零，
  `ElementExpAll` 不变。
- `test_check_profile_current_week_follows_the_clock`：`currentWeek` 等于
  `week_number(now)`，`currentWeek*604800+18000` 落在未来 7 天内，+7 天后序号 +1。
- `test_history_native_numlimit_excludes_current_run_and_failure_does_not_count`
  与 `test_history_legacy_rows_invalid_data_other_players_and_non_element_runs`
  按半月口径补了 `battle_entries` 行并把期望调整到严格上限。

全量 `python -m pytest` 仍有既存失败（`test_battle_entry_domain`、`test_nian_rewards`、
`test_pr19_24_integration`、`test_local_registration`、缺 `work/analysis` 表的
`test_drop_probability_analysis` / `test_favor_seed`），用未修改的工作树复跑同样失败，
与本次改动无关。

## 未做

- 不改 `week_start` / 周光相位（见上）。
- `battle_entries.created_at` 在生产里用 `int(time.time())`，不走注入时钟；测试用
  `UPDATE` 打点来对齐假时钟。生产里入场和刷新是同一条墙钟，无影响。
