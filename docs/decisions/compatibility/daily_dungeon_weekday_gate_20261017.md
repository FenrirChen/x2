---
Document-Type: Compatibility Decision
Domain: Battle
Status: ACTIVE
Updated: 2026-10-17
---
# Decision
再临试炼（DailyDungeon 2030500 饕餮再临 / 2030600 阿波菲斯再临 /
2030700 惩罚者再临 / 2031200 天书再临）的"周几开启"闸门在客户端本地表里，
Revival 侧改为每日全开：用 [tools/patch_daily_dungeon.py](../../../tools/patch_daily_dungeon.py)
把四行的 OpenTime 全置 1，产出两个替换资产
`assets/bin/Data/35da29fb822c44c428ffdfd78d8cc5ee` 与
`assets/bin/Data/c6e1ab33e272eb74a90884182a68f396`，随客户端一起重签。

# Reason
服务端日程（DAILY_COMPAT / always_open）已是全开，但入口仍被客户端挡住：

- `ChapterModule.CheckDailyChapterTime` 0x16bad64：0x16bae84 取 `get_DayOfWeek`，
  0x16bae88 读本地 `DailyDungeon.OpenTime`，0x16baed4 返回 `OpenTime[DayOfWeek] > 0`。
- `ChapterModule.CheckDailyChapterOpenAndLeftTimes` 是该判断与
  `CheckDailyChapterOpenParam` 的与。
- `ChapterModule.OnJump` 的 `param1 == 3` 分支（章节菜单的"再临试炼"入口，
  Jump 29147 -> `ChapterModule(3, 2030500)`）复用同一对判断。

所以"副本刷不了"和"从养成页跳不进去"是同一个闸门，一个修法同时解释两种现象。
`L2C_ServerTableConfig` 只下发字符串键值对，覆盖不到 `OpenTime`，服务端没有杠杆；
服务端入场校验对本日关闭的三关全部放行，且客户端在关闭日根本不会发出
`C2L_FightData(2130501)`。

# Scope
- 只改这四行的 `OpenTime`：每行 3 个 `0 -> 1`（共 12 字节）。奖励、次数、
  `SectionID`、前置条件以及任何服务端行为都不动。
- 客户端资产包里共有 4 份 `DailyDungeon` 副本，工具会全部检查：`table/`
  （35da29fb…）与 `table_392/`（c6e1ab33…）带轮换值，`table_158/` 与
  `table_410/` 本来就是全 1，因此只有前两份产出替换资产。
- 等长替换：保留原 128 字节 RSA 头，明文只做 `0 -> 1`，用同一套位置异或重新
  混淆后签名前缀逐字节不变；`convert_data_bytes` 的掩码与内容无关，所以破坏
  范围就是这 12 个字节。替换文件与参考包内的同名条目除了这 12 字节外逐字节
  相同（serialized file 的数据偏移、对象表和其他对象都不动）。
- 未打补丁的参考包上，工具产出的两个资产 SHA-256：
  `8829b0d437b3bb5b0dd2e5abdace000760b3b12e80cce5db2a096a4a29d92d8f`（table/）
  与 `c13c73329230ac42ae02733fcf0e79e90a6d54cfe63b59ca4b3f6cacb849ea3c`（table_392/）。

# Official
NO（官方把再临试炼限制在固定周几，例如 2030500 的 openTimeDesc 是"一、三、五、周日开启"；
全开是 Revival 的兼容决定）

# User-authorized
YES（USER_DECISION，2026-10-17）

# Usage
```powershell
python tools\patch_daily_dungeon.py --apk <reference.apk> --output <dir>
```
输出目录里是可直接替换同名 zip 条目的资产，外加 `patches.json`（条目 -> 产物路径）
和 `audit.json`（每份副本的改动数与命中 key）。替换后必须用本地开发密钥重新签名
才能安装；工具自己不做签名，也不安装到设备。

# Notes
- 工具只读入参考包，不就地改写；`--output` 与输入必须是不同路径。
- 前置条件（`CheckDailyChapterOpenParam` 的 SectionID 列表）保持原样；新账号
  仍需按正常流程解锁对应章节。
