---
Document-Type: Compatibility Decision
Domain: Shop
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
商店查询/购买/刷新一律明确返回 code 13，不返回成功空列表。

# Reason
官方客户端 ShopModule.OnRefreshShoppingMall 在成功空商品时解引用空集合并崩溃；
错误码分支是安全路径（OnReceiveShopGoodsMsg 0x17A5660 实机依据）。

# Scope
全部 25 店。

# Official
UNKNOWN（官方服务器在停服前的行为不可考）

# User-authorized
YES（NEED.md 记录）
