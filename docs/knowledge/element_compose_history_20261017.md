# 元素之章配方与累计经验跨局保存（PR #56 拓展，2026-10-17）

## 行为

- `Weekly.FormulaComposeAll`、`Weekly.ElementExpAll` 不再始终为零，按服务端已接受的合成记录汇总。当前一局的记录也计入累计，但只计一次。
- 周一 00:00 清理本周战斗断点、光能周进度时，保留合成历史。新局、退出重登、服务重启均恢复累计配方和累计经验。
- 新局与同局重进入场，先发 Weekly，再发 L2C_FightData，避免客户端同步初始化读到旧计数。成功合成以及重复请求回放也同步最新 Weekly。
- 同局 `FightDataProfile` 仍然只包含本局合成次数和本局经验。新局不继承上一局的产物、背包、地图、局内合成等级。
- 合成入口限定为真实、未结束、当前 session 绑定的元素之章关卡。跨周的旧局不能继续生成新合成记录。
- 根据原生 MaxComposeNum 校验 `min(roundLimit, numLimit-(all-single))` 的单次选择上限；0/缺省的限制代表无限。累计与本局计数没有重复相加。

## 客户端证据

文件：`D:/demo/x2/tools/Il2CppDumper-bin/dump.cs`、`script.json` 与 `D:/demo/x2/apk/lib/arm64-v8a/libil2cpp.so`。

- `ElementComposeModule.InitData`（0x14B5978）：0x14B5B10 从 PlayerData+0x68 取 Weekly，+0x20 取 FormulaComposeAll；将其填入 FormulaInfo.allComposeTime（+0x18）。
- 0x14B5BA4 调用的泛型实例由 GOT 0x52A8E28 的 RELA addend 0x5510DC8 定位，实际为 `GetModule<GameSaveModule>()`。共享泛型地址不能直接按 script.json 中最后一个同地址方法名识别。
- 0x14B5BDC 从 GameSaveModule.mGameSaveData+0x50 恢复本局元素经验；0x14B62D4 把 profile 的本局次数直接写入 singleComposeTime（+0x1C），没有再加到 allComposeTime。
- `GameSaveModule.SetGameSaveData`（0x1381E44）先判断入场档案 isProfileValid（0x1381E94）；普通新局 false 不恢复旧局等级。强行伪造 valid 档案也会进入地图、物品等完整恢复链路，本补丁不采用这种做法。
- `ElementComposeModule.MaxComposeNum`（0x14B7034）：0x14B719C–0x14B7200 计算 roundLimit 与 numLimit-(all-single) 的较小值。

累计经验保存与“跨局继承局内等级”不是同一功能。本轮先恢复前者，保留原版新局等级规则；客户端改动仍待用户单独确认。

## 旧数据和完整存档

直接复用 `battle_element_compose` 与 `economy_runs`。按关卡静态表识别元素之章，不依赖 BattleService 初始化后才添加的 section_type 列，兼容旧数据库及服务初始化顺序。

无新表、无逐次叠加迁移标记，也不在 JSON 中保存额外 run UUID。已有合成历史无需迁移即可恢复；没有历史记录的配方不凭空解锁。未知配方、非法计数、孤立记录、其他玩家和非元素之章记录不进入累计。

两张原有表均处于完整存档导出/导入边界；跨账号导入会一起改写 run UUID。重复导入替换存档记录，不把同一批经验再次累加。全程不发放新的局外物品。


## 验证与本地部署

- 累计历史、PR 整合、周刷新、原元素合成及任务回归：29 passed，1 deselected（36.61s）。
- 登录集成、普通战斗、经济操作、完整存档回归：50 passed（53.20s）。
- 被排除的旧顾客交易用例 `test_recurring_customer_trades_count_separately_but_retry_does_not` 预期 10、实际 22；用 a012b0e 的三个未修改生产模块执行也同样失败（1.28s），不属于本次回归。
- 2026-10-17 09:11:52 已重启本地服务；connectInfo 返回 local，三个服务端口就绪。测试玩家快照、家园和赛季状态与重启前完全一致，数据库 quick_check=ok。
- 备份：runtime/before_element_history_20261017_091152/player.sqlite3；未覆盖活跃库。
- 本轮不改 APK，不推送远程。客户端 UI 留给用户手动验收。
