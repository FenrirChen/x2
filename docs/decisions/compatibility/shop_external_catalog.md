# Compatibility shop catalog

Status: **USER_DECISION / REVIVAL_COMPATIBILITY**.

Source: `other/9.25 loadbyhoshi` and `other/9.26 修复包`; the latter supplies the broader 145-slot candidate directory. The current project's 15 directly linked shop 809 offers retain priority. The compatibility export contains the other 130 contributor slots.

The client tables recover the shop protocol, ShopConfig, ShopGoodsGroup, GoodsID, price, currency and limit *kind*. Most GoodsID → ItemID/Num pairings and all limit *counts* lived on the lost official server. Contributor observations and reconstructions fill those gaps for playability. They are not official recovered data.

Current behavior: shops with supported reward destinations list and sell compatibility offers through the current `RewardGrant`, inventory, currency snapshots, SQLite purchase receipts and counts. Unsupported item destinations are withheld from listings. Limited offers use a compatibility cap of one per listed period (day, week, month or lifetime), since the official count is unknown. Shop 804's equipment instance pool is outside this catalog. The existing shop 809 mappings remain unchanged.

Replacement condition: replace the contributor pairings, quantities, prices where unverified, and limit counts when an original server capture, official server data, or stronger client evidence becomes available. Preserve existing purchases through a data migration if the identities or limits change.
