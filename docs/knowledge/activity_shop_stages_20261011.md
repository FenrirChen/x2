# 活动商店阶段列表与购买详情

活动商店总览此前仅包含服务端判为已解锁的阶段，客户端无法显示后续阶段入口。现 `activity_listing` 按阶段排序发送当前主题所有阶段及真实商品，其他主题商店仍不发送。该预览不授予购买资格：普通商店查询、购买详情与支付均继续检查原有条件。覆盖冬至万物3阶段、伪生樱之岛4阶段、全景裂隙4阶段、日月盈仄4阶段。

`L2C_QueryGoodsInfo` 的协议仅包含 code、shopId、goodsId、price、originalPrice、hasBuyTimes、canBuyTimes、itemNum、currencyType。活动实现原先直接复用列表商品对象，混入 itemId、num、startTime 等不合法字段。现在明确返回协议支持的字段，并对15个阶段的全部商品逐一编码解码验证。

购买窗 `ShopCheckWnd.OnOpen` 从选中 `L2C_Goods.itemId` 调用 `CommonItem.SetItem`，随后 `Refresh`，使用客户端资源；与列表使用同一商品物品ID。购买详情协议没有独立图标路径字段。本轮按用户要求不修改客户端资源引用或APK，购买窗图标空白保留，未声称已修复。

测试覆盖完整阶段可见、未解锁查询/购买拒绝、达成条件后开放、全商品购买详情、原有扣料发奖限购与换期重置。重启前备份测试数据库，保留当前伪生樱之岛验收期。没有提交或推送。
