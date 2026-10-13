# 起源悖论商店及界面核对（2026-10-13）

## 服务端身份
固定活动74001、商店活动74002、活动组16、通行证10000、商店898、门票1202901。只发布这两个赛季活动，不借用74004/月相明暗或74007/暇裕时光。
旧存档last_config若不属于起源悖论则归一到对应起源悖论层级，保留已获经验和商店限购。实际数据库原本即为2090001（起源第一阶）；该规则防止导入的其他赛季页面编号进入响应。

## 商店
按用户提供表建立53商品：第1阶段9件，其余阶段各11件。开启经验0/20000/40000/60000/80000对应通行证0/20/40/60/80级。
商店代币1237998，CurrencyType998，与既有BaseInfo.BattlepassShopCoin一致。入场券1202901（本赛季战斗扣除同一物品）。日月之轨·吉尔达1206036，每份1，阶段限购2/3/4/5。神权拓本暂按空白1202080配置，等待用户名称澄清。
全部物品数量、价格、库存见data/origin_season_shop.json。沿用原客户端已知GoodsID，不制造客户端缺失的静态商品编号。原20级只有10个静态货位，新增第11项10分钟卡复用第1阶段未使用的1970901；服务端在20级前不下发该商品，查询和购买同样检查20级门槛。
客户端商店的原ShopParam2按GoodsGroup定位经验门槛；本次仅下发已达到阶段的商品，避免静态门槛高于本轮批准门槛的问题。
库存按season_state.shop_counts保存，回执使用season_receipts。扣币、发货、库存与回执同事务，奖励失败全回滚。周任务刷新不清空商店限购；换新赛季实例才重置。存档导出/导入自然包含原season_state、season_receipts，无新存档边界表。

## 客户端界面限制（本轮未修改APK）
原生MainPage.RefreshBattlePassIcon(0x13d99c0)按ActivityGroup映射切换三种固定按钮；BattlePassModule.GetBattlePassSeason(0x18583b4)把16/23/34映射到1/2/3。
ActivityInfo.get_ActivityGroup(0x1324668)对大活动优先读取客户端ActivityReal静态表；服务端重复下发activityGroup并不能替换本地预制资源。
BattlePassModule.GetBattlePassMainPrefab(0x1858d9c)可以按活动组选择Main/Main2/Main3，但GetBattlePassFarmPrefab(0x1858e80)不论活动组都返回UI_BattlePass_Farm。原APK这个资源资产为a5a8dddd9451d0a4d8547a165ea974da。赛季图标和关卡页面主题图依赖APK中的预制体/图集引用。
因此不能宣称本次服务器修复已把玩家所见暇裕/月相图片换成起源。用户此前要求先不修改客户端，本轮维持该限制。后续客户端统一需核对实际安装APK的主城赛季按钮、ActivityReal条目74001/74002及UI_BattlePass_Farm图集引用，将起源分支资源绑定到起源素材，不改变其他赛季的数据。
