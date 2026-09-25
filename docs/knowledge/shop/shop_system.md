---
Document-Type: Current Knowledge
Domain: Shop
Status: AUTHORITATIVE
Updated: 2026-09-25
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
- **当前运行**：查询/购买/刷新固定拒绝（code 13）——官方客户端在成功空商品时
  `ShopModule.OnRefreshShoppingMall` 空引用崩溃，必须走错误码分支（NEED.md 实机依据）。
- 关键方法：OnReceiveShopGoodsMsg(0x17A5660)、OnRefreshShoppingMall、GetInterval(0x17A7450)、
  CalNumPrice(0x1797A08)——RefreshInterval 是**数量分档阈值**不是刷新时间。
