# SAVE_ROUNDTRIP_VALIDATION.md — 存档往返一致性验证报告

任务：存档管理（导出/导入）核心验收（任务第十八、十九节）。
运行方式：`python tools/savemanager/run_roundtrip_validation.py`（隔离 SQLite，完整生产 schema）。
单测：`python -m pytest tests/unit/test_save_manager.py tests/integration/test_save_manager_http.py`（31 项）。

## 验证链

```
创建 test account A（+B 用于 cross-account）
    ↓ 构造复杂状态（全 60 张边界表每表至少 1 行真实 schema 数据；
      snapshot 含 2 个英雄、装备实例、镶嵌、技能、好感度）
SNAPSHOT_A  = canonical_state(A)
    ↓ export        → SAVE_A（4,645 bytes 容器）
    ↓ 任意变化（金币/等级/新道具/新装备/删除道具/新邮件/成就/任务/战斗收据…）
SNAPSHOT_B  ≠  SNAPSHOT_A   ✅（确认变更真实落地）
    ↓ import SAVE_A（单事务，含 PRE_IMPORT_BACKUP）
SNAPSHOT_C  ==  SNAPSHOT_A  ✅（canonical 完全相等）
```

允许差异仅为 SAVE_DATA_AUDIT.md 第 5 节 EXCLUDED_FROM_SAVE 定义的技术/身份字段
（canonical_state 已排除：players.account/created_at/login_count/revision、accounts 整表、
repair_history、自增序列、surrogate id 按 (type_id,marker)/(uuid,digest) 规范化）。
所有 gameplay state 逐表逐行完全一致。

## 结果汇总

| 快照 A | export 容器 4,645 bytes |
| 快照 B ≠ 快照 A | 变更覆盖经济/养成/邮件/成就/任务/战斗 |
| 快照 C == 快照 A | **ROUND-TRIP PASS**（canonical 相等，无差异） |

## 逐表验证（导出 row count / 恢复 row count / canonical SHA256）

| 表 | 导出 row count | 恢复 row count | 变更后(B)行数 | A/B checksum | C checksum | C==A |
|---|---|---|---|---|---|---|
| achievement_events | 1 | 1 | 1 | `7878cfa69cbc51b9` | `7878cfa69cbc51b9` | ✅ |
| achievement_receipts | 1 | 1 | 1 | `913fdd2d99dba79e` | `913fdd2d99dba79e` | ✅ |
| achievements | 1 | 1 | 2 | `04c3318ad8861a13` | `6cfeb339a3df3473` | ✅ |
| appearance_shop_purchases | 1 | 1 | 1 | `7505800d9fa64c2a` | `7505800d9fa64c2a` | ✅ |
| appearance_shop_receipts | 1 | 1 | 1 | `d7eab79db8c2be73` | `9750cd5d36f6ad3d` | ✅ |
| appearance_voice_unlock | 1 | 1 | 1 | `dadc18faa74b192e` | `dadc18faa74b192e` | ✅ |
| appearance_wear | 1 | 1 | 1 | `e10b92c7a9521cd5` | `e10b92c7a9521cd5` | ✅ |
| bag_jewel_seen | 1 | 1 | 1 | `7d746ecbb9ea00de` | `7d746ecbb9ea00de` | ✅ |
| bag_operation_receipts | 1 | 1 | 1 | `3880397825299453` | `3880397825299453` | ✅ |
| battle_costs | 1 | 1 | 1 | `daef628566a4cfbf` | `ec9dcb3031a8aa9f` | ✅ |
| battle_entries | 1 | 1 | 2 | `79622b22589a3d83` | `89cff85f0860b8b5` | ✅ |
| battle_shop_pickups | 1 | 1 | 1 | `c01efe832fa2337b` | `c01efe832fa2337b` | ✅ |
| battle_shop_purchases | 1 | 1 | 1 | `3218c699902f65f7` | `3218c699902f65f7` | ✅ |
| battle_shop_visits | 1 | 1 | 1 | `51684066be412bbb` | `51684066be412bbb` | ✅ |
| battle_unresolved_rewards | 1 | 1 | 1 | `c3d9afa4f27ff90d` | `9dd33ba867b6ee32` | ✅ |
| challenge_task_state | 1 | 1 | 1 | `78cdea2887fb8121` | `78cdea2887fb8121` | ✅ |
| chapter_dp_floors | 1 | 1 | 1 | `b27b86c25b3214f6` | `b27b86c25b3214f6` | ✅ |
| chapter_dp_migrations | 1 | 1 | 1 | `67340fc969961f78` | `67340fc969961f78` | ✅ |
| chapter_objectives | 1 | 1 | 1 | `b9740d5e5c667c46` | `b9740d5e5c667c46` | ✅ |
| chapter_signals | 1 | 1 | 1 | `6249d9def6a53cfb` | `6249d9def6a53cfb` | ✅ |
| collection_awards | 1 | 1 | 1 | `55c94449905a6404` | `55c94449905a6404` | ✅ |
| college_state | 1 | 1 | 1 | `a1ad4cfafb8acdb5` | `a1ad4cfafb8acdb5` | ✅ |
| economy_checkouts | 1 | 1 | 1 | `e7dec3a5845871b7` | `a612ae62c6acae01` | ✅ |
| economy_clears | 1 | 1 | 1 | `1269a0d5387b0290` | `1269a0d5387b0290` | ✅ |
| economy_events | 1 | 1 | 1 | `6297e1af473f3925` | `6297e1af473f3925` | ✅ |
| economy_grants | 1 | 1 | 1 | `42282864d858c95b` | `42282864d858c95b` | ✅ |
| economy_runs | 1 | 1 | 2 | `5347f1d15280b9ce` | `9afa05a562cc9868` | ✅ |
| economy_tasks | 1 | 1 | 1 | `31444b27b1d71573` | `31444b27b1d71573` | ✅ |
| equipment_enhancements | 1 | 1 | 1 | `828a62c53b66a157` | `828a62c53b66a157` | ✅ |
| equipment_instances | 2 | 2 | 3 | `1d0d96a8bddaa04a` | `f65628921d839937` | ✅ |
| equipment_main_growth | 1 | 1 | 1 | `847ee09ff5abf650` | `847ee09ff5abf650` | ✅ |
| favor_touch_log | 1 | 1 | 1 | `02a8632d8d3dfc9c` | `02a8632d8d3dfc9c` | ✅ |
| fight_drop_observations | 1 | 1 | 1 | `185a83e4998596b3` | `185a83e4998596b3` | ✅ |
| gift_package_claims | 1 | 1 | 1 | `e18f72367a278c71` | `e18f72367a278c71` | ✅ |
| gift_package_daily_claims | 1 | 1 | 1 | `8ea4bbd1e0ae635d` | `8ea4bbd1e0ae635d` | ✅ |
| gift_package_receipts | 1 | 1 | 1 | `5e1953eab07bc788` | `5d00d5b95c35bf55` | ✅ |
| inventory | 1 | 1 | 2 | `b6490d1c82c94027` | `7c5e4b737ae20334` | ✅ |
| item_opt_receipts | 1 | 1 | 1 | `47ea3e3a43b7ce19` | `d7eab79db8c2be73` | ✅ |
| pending_reward_instances | 1 | 1 | 2 | `bf0c0d9ff9bdf027` | `954686cacf2e1bd7` | ✅ |
| pending_rewards | 1 | 1 | 1 | `0b3994bd59f50f73` | `0b3994bd59f50f73` | ✅ |
| player_mail | 3 | 3 | 4 | `c85b1d723d91f8c2` | `aab3d841e53356ef` | ✅ |
| progression_receipts | 1 | 1 | 1 | `cbca70bf93a70e51` | `cbca70bf93a70e51` | ✅ |
| reward_settlement_audit | 1 | 1 | 1 | `bbb940788e51ef0c` | `e7a1e3b4b2694083` | ✅ |
| shop_compat_counts | 1 | 1 | 1 | `428b1a71129ef184` | `428b1a71129ef184` | ✅ |
| shop_purchase_counts | 1 | 1 | 1 | `aca119686445ee5f` | `aca119686445ee5f` | ✅ |
| shop_receipts | 1 | 1 | 1 | `56a27ddd94a40125` | `5e1953eab07bc788` | ✅ |
| shop_refreshes | 1 | 1 | 1 | `49ad0e7ee83b7429` | `49ad0e7ee83b7429` | ✅ |
| star_chart_receipts | 1 | 1 | 1 | `55bb34f4f26403d1` | `55bb34f4f26403d1` | ✅ |
| sweep_receipts | 1 | 1 | 1 | `cbc74e5b7f8b55bc` | `eab9e99bd1d21d33` | ✅ |
| task_boxes | 1 | 1 | 1 | `7f55e855c196e568` | `7f55e855c196e568` | ✅ |
| task_history | 1 | 1 | 2 | `676a634e4e7cd2ca` | `f5c476bfe6ee1afb` | ✅ |
| task_periods | 1 | 1 | 1 | `d51918256d8a9c2c` | `d51918256d8a9c2c` | ✅ |
| wish_last_result | 1 | 1 | 1 | `539c90ff48240e0d` | `539c90ff48240e0d` | ✅ |
| wish_pity | 1 | 1 | 1 | `c83581661953dc4b` | `c83581661953dc4b` | ✅ |
| wish_receipts | 1 | 1 | 1 | `342a569fec0bf407` | `342a569fec0bf407` | ✅ |
| wish_state | 1 | 1 | 1 | `d80946e6f89075aa` | `d80946e6f89075aa` | ✅ |
| battle_checkout_wire | 1 | 1 | 1 | `20d60e37e5a397db` | `20d60e37e5a397db` | ✅ |
| battle_receipts | 1 | 1 | 2 | `8acde14f00de8424` | `7b8eecd3a00cc1b6` | ✅ |
| fight_drop_claims | 1 | 1 | 1 | `2f68cbe64a70e4b1` | `2f68cbe64a70e4b1` | ✅ |
| fight_drop_items | 1 | 1 | 1 | `a33d0028b8079f88` | `a33d0028b8079f88` | ✅ |

## Cross-account 验证

| 检查 | 结果 |
|---|---|
| B 导入 A 存档后 canonical(B) == canonical(A 导出前) | ✅ |
| B 的账号名/密码/PBKDF2 哈希未被覆盖（pw-beta 仍可验证） | ✅ |
| equipment_instances 实例 id 与 A 无交集（owner remap） | ✅ |
| B 的 equipment_enhancements/growth 引用全部指向 B 自己的实例 | ✅ |


## 判定

- **ROUND-TRIP PASS**：导出快照 == 导入恢复快照（60/60 表逐表 checksum 相等）。
- 变更阶段（B）checksum 与 A/C 不同的表证明变更真实发生且被导入完整回滚到 A。
- 安全/异常路径（31 项自动化测试覆盖）：坏档、缺表、多表、错列、错型、player_id 不一致、
  引用悬空、非法 zip 条目、重复条目、错误版本、错误密码、不存在账号、在线账号 409、
  导入后 token 失效、强制中途失败整体 ROLLBACK、PRE_IMPORT_BACKUP 不覆盖且可再导入、
  序列前推、跨号导入身份保留与 ID remap。

状态：**PASS**（服务端逻辑层面；真机端到端回归见 FINAL_SAVE_MANAGER_VALIDATION.md 第 14 节）。
