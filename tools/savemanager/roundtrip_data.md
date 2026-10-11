| 快照 A | export 容器 6,117 bytes |
| 快照 B ≠ 快照 A | 变更覆盖经济/养成/邮件/成就/任务/战斗 |
| 快照 C == 快照 A | **ROUND-TRIP PASS**（canonical 相等，无差异） |

## 逐表验证（导出 row count / 恢复 row count / canonical SHA256）

| 表 | 导出行数 | 恢复后行数 | 恢复前(B)行数 | B checksum | C checksum | C==A |
|---|---|---|---|---|---|---|
| achievement_events | 1 | 1 | 1 | `7878cfa69cbc51b9` | `7878cfa69cbc51b9` | ✅ |
| achievement_receipts | 1 | 1 | 1 | `913fdd2d99dba79e` | `913fdd2d99dba79e` | ✅ |
| achievements | 1 | 1 | 2 | `04c3318ad8861a13` | `6cfeb339a3df3473` | ✅ |
| activity_events | 1 | 1 | 1 | `010a9f5fb72b552a` | `010a9f5fb72b552a` | ✅ |
| activity_receipts | 1 | 1 | 1 | `a1fecd6c362e30ad` | `a1fecd6c362e30ad` | ✅ |
| activity_runs | 1 | 1 | 1 | `da841c89d1953114` | `da841c89d1953114` | ✅ |
| activity_state | 1 | 1 | 1 | `e12dda007008b879` | `e12dda007008b879` | ✅ |
| appearance_shop_purchases | 1 | 1 | 1 | `92a3b967e2c76aa9` | `92a3b967e2c76aa9` | ✅ |
| appearance_shop_receipts | 1 | 1 | 1 | `2827d02903a243f7` | `56a27ddd94a40125` | ✅ |
| appearance_voice_unlock | 1 | 1 | 1 | `6a59a574ed693cb1` | `6a59a574ed693cb1` | ✅ |
| appearance_wear | 1 | 1 | 1 | `d9610f17cd1aaf45` | `d9610f17cd1aaf45` | ✅ |
| bag_jewel_seen | 1 | 1 | 1 | `cdf2563ebbe9c327` | `cdf2563ebbe9c327` | ✅ |
| bag_operation_receipts | 1 | 1 | 1 | `6cbc7ed5724f4058` | `6cbc7ed5724f4058` | ✅ |
| battle_costs | 1 | 1 | 1 | `1429c80e13e0f91c` | `982d1c96c637e6ff` | ✅ |
| battle_entries | 1 | 1 | 2 | `659c0d18891c86e6` | `6245dabba400a1d8` | ✅ |
| battle_shop_pickups | 1 | 1 | 1 | `54363c5568d5725b` | `54363c5568d5725b` | ✅ |
| battle_shop_purchases | 1 | 1 | 1 | `0e283e4591f8a6f0` | `0e283e4591f8a6f0` | ✅ |
| battle_shop_visits | 1 | 1 | 1 | `027bd20ea87675f3` | `027bd20ea87675f3` | ✅ |
| battle_unresolved_rewards | 1 | 1 | 1 | `33be08d4b7b28bde` | `7054698800af9ec7` | ✅ |
| challenge_task_state | 1 | 1 | 1 | `2a1174e1a925576f` | `2a1174e1a925576f` | ✅ |
| chapter_dp_floors | 1 | 1 | 1 | `63269579952e5d2d` | `63269579952e5d2d` | ✅ |
| chapter_dp_migrations | 1 | 1 | 1 | `469bcdc9c231c48b` | `469bcdc9c231c48b` | ✅ |
| chapter_objectives | 1 | 1 | 1 | `4158ff9868fd2f11` | `4158ff9868fd2f11` | ✅ |
| chapter_signals | 1 | 1 | 1 | `9409b433fefc52cc` | `9409b433fefc52cc` | ✅ |
| collection_awards | 1 | 1 | 1 | `5b684cce2166323c` | `5b684cce2166323c` | ✅ |
| college_alchemy_receipts | 1 | 1 | 1 | `381da30d656e9561` | `381da30d656e9561` | ✅ |
| college_job_receipts | 1 | 1 | 1 | `68e1443af8e031fd` | `68e1443af8e031fd` | ✅ |
| college_pray_receipts | 1 | 1 | 1 | `0a3547e84c60ff5c` | `0a3547e84c60ff5c` | ✅ |
| college_state | 1 | 1 | 1 | `a1ad4cfafb8acdb5` | `a1ad4cfafb8acdb5` | ✅ |
| college_upgrade_receipts | 1 | 1 | 1 | `5f7c60cd46c34ddd` | `5f7c60cd46c34ddd` | ✅ |
| economy_checkouts | 1 | 1 | 1 | `f06b43ae88014fdb` | `04c8e1d1555f7bc9` | ✅ |
| economy_clears | 1 | 1 | 1 | `d1a266f089525c69` | `d1a266f089525c69` | ✅ |
| economy_events | 1 | 1 | 1 | `873f88a55098e200` | `873f88a55098e200` | ✅ |
| economy_grants | 1 | 1 | 1 | `ba8a12e738b25c04` | `ba8a12e738b25c04` | ✅ |
| economy_runs | 1 | 1 | 2 | `a1e2df23ac0288ae` | `bbbdfe760fad332d` | ✅ |
| economy_tasks | 1 | 1 | 1 | `4dbca77997aa41bb` | `4dbca77997aa41bb` | ✅ |
| endless_observations | 1 | 1 | 1 | `2f64f0f04bc4e10f` | `2f64f0f04bc4e10f` | ✅ |
| endless_profiles | 1 | 1 | 1 | `10e80ee25684fa08` | `10e80ee25684fa08` | ✅ |
| endless_task_receipts | 1 | 1 | 1 | `4e56b312e17fa0ac` | `4e56b312e17fa0ac` | ✅ |
| endless_tasks | 1 | 1 | 1 | `c884ec3da145e16c` | `c884ec3da145e16c` | ✅ |
| equip_plan_receipts | 1 | 1 | 1 | `872d468be915b196` | `c90e020d50d7e841` | ✅ |
| equipment_enhancements | 1 | 1 | 1 | `39987f5ba0ea1c7b` | `39987f5ba0ea1c7b` | ✅ |
| equipment_instances | 2 | 2 | 3 | `4e7dd7544d266783` | `5ea78f03390f9b8b` | ✅ |
| equipment_lock_receipts | 1 | 1 | 1 | `1ca8139b390c00df` | `47ea3e3a43b7ce19` | ✅ |
| equipment_main_growth | 1 | 1 | 1 | `dd5e56648cd8b642` | `dd5e56648cd8b642` | ✅ |
| favor_touch_log | 1 | 1 | 1 | `fcc76e622525dc62` | `fcc76e622525dc62` | ✅ |
| fight_drop_observations | 1 | 1 | 1 | `b751403bf63743e9` | `b751403bf63743e9` | ✅ |
| gift_package_claims | 1 | 1 | 1 | `b5db560d52d80db9` | `b5db560d52d80db9` | ✅ |
| gift_package_daily_claims | 1 | 1 | 1 | `f9f68c3710618699` | `f9f68c3710618699` | ✅ |
| gift_package_receipts | 1 | 1 | 1 | `d08832bc86fe0886` | `1ca8139b390c00df` | ✅ |
| inventory | 1 | 1 | 2 | `ba11f0d23e12564e` | `7eafdc4b7c5416ad` | ✅ |
| item_opt_receipts | 1 | 1 | 1 | `52cb13d70e536a72` | `2827d02903a243f7` | ✅ |
| pending_reward_deliveries | 1 | 1 | 1 | `ae77eccd6417f469` | `ae77eccd6417f469` | ✅ |
| pending_reward_instances | 1 | 1 | 2 | `f877e5835805676a` | `2da18b63080f27f7` | ✅ |
| pending_rewards | 1 | 1 | 1 | `24811a13b6064925` | `24811a13b6064925` | ✅ |
| player_mail | 5 | 5 | 6 | `ad8689a7c633d359` | `b15671f86d7ac011` | ✅ |
| progression_receipts | 1 | 1 | 1 | `a1b28e306371cb6f` | `a1b28e306371cb6f` | ✅ |
| reward_settlement_audit | 1 | 1 | 1 | `d484eeda1076ae79` | `5a8b4e6c1cf5bfc4` | ✅ |
| shop_compat_counts | 1 | 1 | 1 | `3b1a57e9185181ff` | `3b1a57e9185181ff` | ✅ |
| shop_purchase_counts | 1 | 1 | 1 | `297c29b01f759312` | `297c29b01f759312` | ✅ |
| shop_receipts | 1 | 1 | 1 | `6b030a9b86767965` | `d08832bc86fe0886` | ✅ |
| shop_refreshes | 1 | 1 | 1 | `950ec88a95636cdf` | `950ec88a95636cdf` | ✅ |
| star_chart_receipts | 1 | 1 | 1 | `b71750a2543e6652` | `b71750a2543e6652` | ✅ |
| story_reviews | 1 | 1 | 1 | `e6fbef4356b7192d` | `e6fbef4356b7192d` | ✅ |
| sweep_receipts | 1 | 1 | 1 | `12c95df95c37dd99` | `12c95df95c37dd99` | ✅ |
| task_boxes | 1 | 1 | 1 | `df591ff4df0ec23f` | `df591ff4df0ec23f` | ✅ |
| task_history | 1 | 1 | 2 | `068beca086872750` | `3b7610776de90aa4` | ✅ |
| task_periods | 1 | 1 | 1 | `4eb14c22ceb5fe75` | `4eb14c22ceb5fe75` | ✅ |
| wish_last_result | 1 | 1 | 1 | `6125be7d7f68df93` | `6125be7d7f68df93` | ✅ |
| wish_pity | 1 | 1 | 1 | `5f04aaa1b15b1479` | `5f04aaa1b15b1479` | ✅ |
| wish_receipts | 1 | 1 | 1 | `8a90b9ff9dd526d4` | `8a90b9ff9dd526d4` | ✅ |
| wish_state | 1 | 1 | 1 | `619262560a8d5b67` | `619262560a8d5b67` | ✅ |
| world_boss_accounts | 1 | 1 | 1 | `eaebe78608675ac8` | `eaebe78608675ac8` | ✅ |
| world_boss_members | 1 | 1 | 1 | `017b7296ac159638` | `f6167e0b04ab03d1` | ✅ |
| world_boss_player_days | 1 | 1 | 1 | `e35ffa2adb57156b` | `e4f4d8544e3a0794` | ✅ |
| world_boss_receipts | 1 | 1 | 1 | `16406dd723b934d1` | `16406dd723b934d1` | ✅ |
| world_boss_tickets | 1 | 1 | 1 | `133000d956bec3ff` | `f58cadc87f3765a5` | ✅ |
| battle_checkout_wire | 1 | 1 | 1 | `95284264ff277bab` | `95284264ff277bab` | ✅ |
| battle_drop_budget_versions | 1 | 1 | 1 | `f022296c0ca8a163` | `f022296c0ca8a163` | ✅ |
| battle_receipts | 1 | 1 | 2 | `9e250b045d119187` | `88679efc982cd504` | ✅ |
| fight_drop_claims | 1 | 1 | 1 | `b004d23d4cc85e07` | `b004d23d4cc85e07` | ✅ |
| fight_drop_items | 1 | 1 | 1 | `1688470797264dd7` | `1688470797264dd7` | ✅ |
| world_boss_runs | 1 | 1 | 1 | `7c895c45aeb0a9b5` | `86259c4b950084ea` | ✅ |

## Cross-account 验证

| 检查 | 结果 |
|---|---|
| B 导入 A 存档后 canonical(B) == canonical(A 导出前) | ✅ |
| B 的账号名/密码/PBKDF2 哈希未被覆盖（pw-beta 仍可验证） | ✅ |
| equipment_instances 实例 id 与 A 无交集（owner remap） | ✅ |
| B 的 equipment_enhancements/growth 引用全部指向 B 自己的实例 | ✅ |
