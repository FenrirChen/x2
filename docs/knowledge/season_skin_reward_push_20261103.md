# 2026-11-03 赛季凭证外观到账后补推外观页

## 现象

远程赛季凭证领到 LV.60「超越凭证」奖励托尔·计划外教学（外观道具 1221203）后，
道具已经进入背包，但「神格外观」页仍显示「未获得」；重新登录后才会恢复。

## 原因

客户端的外观页只在登录的 `heroSkinAll` 与 `L2C_HeroSkinAll` / `L2C_HeroSkinUpdate`
里重读某神格的已拥有形象。旧实现只有外观商店（`appearance_shop`）和活动兑换
（`activity_exchange`）在各自的购买路径里补推，赛季通行证走的是
`EconomyService._grant` 的通用发货通道，没有推送。于是背包里有 1221203，
外观页却一直停留在旧列表。

## 修复

- `EconomyService._grant` 在真正发出 `ItemType == 17` 的道具时，按玩家记下本次
  请求发出的外观号（`_granted_skins`）。
- `EconomyService.pushes()` 末尾由新的 `_skin_pushes` 把待推送外观换算成对应神格的
  `L2C_HeroSkinAll` + `L2C_HeroSkinUpdate`。因此赛季、邮件、活动等任何经过
  `_grant` 的发货路径都会刷新外观页。
- `tools/local_game_server.py` 把 `AppearanceService` 注入 `economy.appearance`；
  未接线时（多数单元测试）发货照常，只是不推送。

外观商店/活动兑换原有的补推保留，行为不变；本次只补上此前漏掉的路径。

## 验证

新增 `tests/unit/test_season_skin_reward_push.py`：

- 真实领取赛季 LV.60 奖励组 798560，断言 1221203 进入背包且数量为 1；
- 断言本次请求的 `EconomyService.pushes()` 含 `L2C_HeroSkinAll`，以及
  `heroId=1012`、`skinIds` 含 1221203 的 `L2C_HeroSkinUpdate`；
- 断言重新登录的已拥有列表（`_owned_skins`）包含 1221203。

赛季、外观、活动兑换、经济等相关 97 项回归通过。全量 `tests/unit` 共 1673 项：
1661 通过、7 失败、6 错误；失败/错误在未修改的 origin/main（8031b83）基线用同样命令
完全复现（`analysis/drop_archaeology` 数据目录缺失、Origin Paradox/年兽环境依赖），
与本次修改无关。未修改客户端、APK、存档格式或既有奖励表。
