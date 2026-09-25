# 重构后知识目录树（2026-09-25）

```
x2_revive_workspace/
├─ PROJECT_INDEX.md            # 新 AI 唯一入口（READ THIS FIRST）
├─ README.md / NEED.md         # 人类入口 / 缺口清单
├─ SESSION_HANDOFF.md          # (仓库外 D:/demo/x2/) 当前运行状态，已精简
│
├─ docs/
│  ├─ README.md                # 文档治理规则（新文档放哪）
│  ├─ PATH_MIGRATION.md        # 旧路径 → 新路径
│  ├─ knowledge/               # ★ 当前权威知识
│  │  ├─ CURRENT_STATE.md
│  │  ├─ architecture/  system_overview.md, server_architecture.md
│  │  ├─ battle/        battle_architecture.md, section_types.md, battle_variant_coverage.md
│  │  ├─ rewards/       reward_system.md, drop_system.md, gift_system.md, special_rewards.md,
│  │  │                 drop_algorithm.md, reward_semantics.md, fightitembag_persistence_boundary.md,
│  │  │                 gift_runtime_semantics.md, special_reward_state_machines.md,
│  │  │                 section_reward_system.md, section_reward_coverage.md, server_fix_plan.md
│  │  ├─ equipment/     equipment_system.md, equipment_instance_generation.md
│  │  ├─ economy/       economy_system.md, client_economy_data_audit.md, missing_evidence_followup.md
│  │  ├─ progression/   progression_system.md
│  │  ├─ shop/          shop_system.md
│  │  ├─ persistence/   persistence_model.md, persistence_relog_audit.md
│  │  ├─ coverage/      runtime_coverage.md, runtime_backlog.md, runtime_coverage_static_reaudit.md,
│  │  │                 false_complete_audit.md, false_complete_elimination.md, known_unknowns.md
│  │  ├─ client/        client_architecture.md, static_table_dictionary.md
│  │  ├─ protocol/      protocol_overview.md, message_catalog_guide.md
│  │  ├─ dev/           development.md, network.md, protocol_spec.md, bootstrap*.md,
│  │  │                 startup_routing.md, gameconfig_resolution.md,
│  │  │                 reverse_engineering_sources.md, android_toolchain_manifest.md,
│  │  │                 all_section_battle_recovery.md
│  │  └─ mission/ tasks/  README.md（证据不足域入口）
│  ├─ history/                 # 时间线 + 被推翻结论 + 33 篇 dated 报告
│  │  ├─ README.md  PROJECT_TIMELINE.md  SUPERSEDED_KNOWLEDGE.md
│  │  └─ 2026-09-2*_NN_*.md
│  └─ decisions/
│     ├─ adr/                  # 5 篇架构决策
│     └─ compatibility/        # gold_dungeon_manual_reward, shop_closed_guard,
│                              # sweep_rules, daily_calendar_beijing
├─ evidence/
│  ├─ README.md
│  ├─ manifests/evidence_manifest.json   # 32 条 Evidence ID（含 SHA256）
│  ├─ raw/{client,protocol,static_tables,runtime_traces}/
│  ├─ derived/README.md        # canonical 索引（分析产物原地保留）
│  └─ external/third_party/    # 第三方工作簿隔离副本
├─ analysis/                   # 派生证据（canonical；含 knowledge_reorg/）
├─ tools/analysis/             # 确定性生成器 + validate_knowledge_base.py
├─ src/ tests/ runtime/ release/
```
