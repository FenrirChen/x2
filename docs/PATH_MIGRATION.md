# PATH_MIGRATION（2026-09-25 知识库重构）

常用旧路径 → 新路径（完整 69 条见 `analysis/knowledge_reorg/migration_map.csv`）：

| 旧 | 新 |
|---|---|
| docs/runtime_coverage_matrix.md | docs/knowledge/coverage/runtime_coverage.md |
| docs/runtime_backlog.md | docs/knowledge/coverage/runtime_backlog.md |
| docs/battle_variant_coverage.md | docs/knowledge/battle/battle_variant_coverage.md |
| docs/section_reward_system.md / _coverage.md | docs/knowledge/rewards/section_reward_system.md / section_reward_coverage.md |
| docs/drop_algorithm_reverse_engineering.md | docs/knowledge/rewards/drop_algorithm.md |
| docs/reward_semantics_reverse_engineering.md | docs/knowledge/rewards/reward_semantics.md |
| docs/fightitembag_persistence_boundary.md | docs/knowledge/rewards/fightitembag_persistence_boundary.md |
| docs/gift_runtime_semantics.md | docs/knowledge/rewards/gift_runtime_semantics.md |
| docs/special_reward_state_machines.md | docs/knowledge/rewards/special_reward_state_machines.md |
| docs/reward_system_server_fix_plan.md | docs/knowledge/rewards/server_fix_plan.md |
| docs/equipment_instance_generation.md | docs/knowledge/equipment/equipment_instance_generation.md |
| docs/client_economy_data_audit.md | docs/knowledge/economy/client_economy_data_audit.md |
| docs/economy_missing_evidence_followup.md | docs/knowledge/economy/missing_evidence_followup.md |
| docs/client_progression_data_audit.md | docs/knowledge/progression/progression_system.md |
| docs/client_static_table_dictionary.md | docs/knowledge/client/static_table_dictionary.md |
| docs/persistence_relog_audit.md | docs/knowledge/persistence/persistence_relog_audit.md |
| docs/false_complete_audit.md / _elimination.md | docs/knowledge/coverage/ |
| docs/architecture.md | docs/knowledge/architecture/server_architecture.md |
| docs/development.md / network.md / protocol_spec.md / bootstrap*.md / startup_routing.md / gameconfig_resolution.md / reverse_engineering_sources.md / android_toolchain_manifest.md / all_section_battle_recovery.md | docs/knowledge/dev/ |
| docs/adr/ | docs/decisions/adr/ |
| docs/phase*_*.md（各阶段报告） | docs/history/YYYY-MM-DD_NN_* |
| docs/milestones.md / android_lab*.md / first_contact_*.md / mumu_migration.md / daily_dungeon_reward_audit.md / gold_dungeon_drop_clues.md / shop_recovery_from_workbook.md | docs/history/ |
| docs/project_knowledge_index.md | /PROJECT_INDEX.md（本文件同级的仓库根） |
| docs/*_evidence.json | evidence/raw/runtime_traces/ |
| D:/demo/x2/docs/deep_drop_archaeology.md | docs/history/2026-09-24_07_deep_drop_archaeology.md |
| D:/demo/x2/docs/drop_graph_audit.md | docs/history/2026-09-24_08_drop_graph_audit.md |
| D:/demo/x2/docs/dropvalue_code_path.md | docs/history/2026-09-24_09_dropvalue_code_path.md |
| D:/demo/x2/docs/external_dataset_crosscheck.md | docs/history/2026-09-25_02_external_dataset_crosscheck.md |

保持不动（脚本/运行时依赖）：`analysis/**`（canonical 已登记 evidence manifest）、
`src/x2server/data/**`、`analysis/progression/*.json`（EquipmentService 运行时读取）、
仓库外 `D:/demo/x2/{phase2_output,phase3_output,analysis,tools}`。
