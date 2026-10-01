# 战斗永久属性加成恢复（2026-10-01）

## 现场证据

玩家 1，11:30:46，关卡 2110152，回执
`0d5304c7-87b4-454b-91b5-855f3e0a1a69`：神格 1028 基础攻击 1563，
魂器 1528 等级 100、星级 6，宝石 1250083；有一件兽主，无套装。
旧回包缺少 `heroGodEquip.godEquipAttr`，`attrAdd` 也没有羁绊/文明属性。
因此角色页从静态表算出的增益没有进入战斗。角色页总属性不能当作裸基础属性再次发送，
否则战斗客户端会再叠加装备一次。

## 客户端规则与完整来源核对

`ClientProperty.Init` (0x1491514) 依次加入基础属性、兽主、魂器/宝石、文明、羁绊。
成长、技能等级、魂器神权技能、战斗皮肤已经通过现有字段发送。
兽主原始强化词条通过 `heroEquip`，两件属性及四件被动通过 `equipSuitAttr`，保持上轮实现。
已选择神迹通过 `selectedRelicList`/战斗 profile，保持现有持有校验。
未实现、未持有的赛季/天赋数据没有凭空赋予。

- `ClientProperty.AddHeroGodEquipAttributes` 0x1491e48：
  `factor = (AttrRate + level * (MaxAttrRate - AttrRate) * 0.01f) * 0.001f`。
  整数乘积后转换 float32；最终每项截断为 int32。升阶属性数组索引为 star。
- `ChapterModule.ConvertHeroGodEquip` 0x16c2d4c：战斗只把 `godAttr`、
  `jewelAttr.effect1` 转为属性，`jewelAttr.effect2` 转为被动。
  仅提供魂器等级、宝石 ID 无法代替这些属性载体。
- `Player.OnInitProperty` 0x1c1755c / `Property.AddHeroGodEquipAttributes` 0x1c17bc4：
  在基础上叠加这些增益。`HeroAttrCount` 仍是裸神格成长基础。
- `ClientProperty.AddFettersAttributes` 0x1492df8：仅 IsOpen 羁绊，索引 level-1。
- `CollegeWonderModule.Civilization.Refresh` 0x1db5748：文明建筑按星级解锁技能，
  属性数组索引建筑 level-1；`GetCivilizationFromOrigin` 0x1db6484 仅返回同源文明。
  零星不解锁。逆位 Origin=9 使用 `GlobalParamString.InversionWonderSkill` 的末值，
  为客户端已有特殊规则，不依赖玩家文明建筑进度。

1028 的魂器应下发攻击 1008、防御 612、生命 5904、攻击百分比属性 1200、冰伤属性 720；
宝石冰伤属性 168；羁绊位置 3、等级 3 为生命百分比属性 240。
该账号文明建筑零星，目前没有普通文明增益。

## 数据、持久化与验证

静态数据由 `tools/analysis/export_battle_bonuses.py` 从正式 2.4 APK 导出，
运行时无需本地 APK。战斗读取已有快照与文明存档，不修改养成数据。
完整回包继续写入 battle_entries；重放同一请求使用原回执，新的入场读取当前装备/增益。
`tools/diagnose_battle_bonuses.py --database <path> --player <id>` 使用 SQLite mode=ro，
可比较当前保存的加成与最近一次入场回执。修复前的旧回执不会被改写，需新开战斗验证。

测试使用临时数据库，覆盖魂器成长/升阶、普通/特殊宝石、羁绊开关/越界、文明星级/等级/同源、
逆位特殊规则、加成单次下发、装备变更后的新入场与历史请求幂等重放。
