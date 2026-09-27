---
Document-Type: Current Knowledge
Domain: Shop
Status: AUTHORITATIVE
Updated: 2026-09-27
Supersedes:
  - docs/history/2026-09-24_06_shop_recovery_from_workbook.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 商店系统

- **静态（A）**：ShopConfig 25 店（ShopID/类型/刷新/条件）、ShopGoodsGroup 1,567 行
  （GoodsID=19xxxxx 合成 id、价格、货币枚举、限购周期、条件）——第三方工作簿逐字段互证 100%。
- **缺口（SERVER_ONLY）**：GoodsID→ItemID/Num、库存、限购次数、刷新执行、随机店抽取。
  唯一价格样本=第三方"随机商店(实测)"22 条（玩家口述，未验证，
  Evidence: EXTERNAL_WORKBOOK_X2_LOCAL_SERVER）。
- **当前运行**：809 店 15 格沿用 `Item.QuickBuyID` 反查映射；另接入 B 包 130 格候选中的可安全交付商品。查询、购买、扣币、RewardGrant、限购计数、收据和重登状态闭环；无法交付的物品不列出。804 的兽主实例池仍未并入。
- **证据级别**：协议与静态商店外壳属官方客户端证据；外部包商品映射/数量与限购次数属 **REVIVAL_COMPATIBILITY / USER_DECISION**，详见 [兼容决策](../../decisions/compatibility/shop_external_catalog.md)。已启用的限购物品按类别每周期 1 次，是兼容规则，不代表原服数值。
- 关键方法：OnReceiveShopGoodsMsg(0x17A5660)、OnRefreshShoppingMall、GetInterval(0x17A7450)、
  CalNumPrice(0x1797A08)——RefreshInterval 是**数量分档阈值**不是刷新时间。
- **礼包 2700092（用户上架决定，2026-09-27）**：外观券回馈礼包按官方静态价格 99 纯晶石、Gift 781099（外观券 30、1 小时加速卡 3、金币 10000）上架。官方表 `Times=3`，本地目录设不限量；每次成功购买独立扣款/发奖，重试同一请求使用收据去重，列表购买状态保持可购买。客户端是否另按静态 `Times=3` 限制显示仍待实机验证。
