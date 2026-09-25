"""Knowledge reorg step 2: execute the docs/evidence migration with git mv.

- docs/*.md  -> docs/knowledge/<domain>/ (current knowledge, metadata header added)
- docs/*.md  -> docs/history/YYYY-MM-DD_NN_topic.md (historical, metadata header added)
- docs/adr   -> docs/decisions/adr
- docs/*_evidence.json -> evidence/raw/runtime_traces/
- root D:/demo/x2/docs/*.md -> docs/history/ (plain move; root is not a git repo)
Writes analysis/knowledge_reorg/migration_map.csv.
"""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import time
from pathlib import Path

REPO = Path(r"D:\demo\x2\x2_revive_workspace")
ROOT = Path(r"D:\demo\x2")
GIT = ["git", "-c", f"safe.directory={REPO.as_posix()}"]

def git(*args):
    r = subprocess.run(GIT + list(args), cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0 and "did not match" not in r.stderr and "fatal" in (r.stderr or "").lower():
        print("GIT WARN:", args, r.stderr.strip()[:200])
    return r

KNOWLEDGE_MOVES = [
    # (old docs-relative, new knowledge-relative, domain, supersedes list)
    ("runtime_coverage_matrix.md", "coverage/runtime_coverage.md", "Coverage",
     ["docs/history/2026-09-25_02_project_knowledge_index.md"]),
    ("runtime_coverage_static_reaudit.md", "coverage/runtime_coverage_static_reaudit.md", "Coverage", []),
    ("runtime_backlog.md", "coverage/runtime_backlog.md", "Coverage", []),
    ("false_complete_audit.md", "coverage/false_complete_audit.md", "Coverage", []),
    ("false_complete_elimination.md", "coverage/false_complete_elimination.md", "Coverage", []),
    ("battle_variant_coverage.md", "battle/battle_variant_coverage.md", "Battle", []),
    ("section_reward_system.md", "rewards/section_reward_system.md", "Rewards", []),
    ("section_reward_coverage.md", "rewards/section_reward_coverage.md", "Rewards", []),
    ("drop_algorithm_reverse_engineering.md", "rewards/drop_algorithm.md", "Rewards",
     ["docs/history/2026-09-24_03_deep_drop_archaeology.md"]),
    ("reward_semantics_reverse_engineering.md", "rewards/reward_semantics.md", "Rewards", []),
    ("fightitembag_persistence_boundary.md", "rewards/fightitembag_persistence_boundary.md", "Rewards", []),
    ("gift_runtime_semantics.md", "rewards/gift_runtime_semantics.md", "Rewards", []),
    ("special_reward_state_machines.md", "rewards/special_reward_state_machines.md", "Rewards", []),
    ("reward_system_server_fix_plan.md", "rewards/server_fix_plan.md", "Rewards", []),
    ("equipment_instance_generation.md", "equipment/equipment_instance_generation.md", "Equipment", []),
    ("economy_missing_evidence_followup.md", "economy/missing_evidence_followup.md", "Economy", []),
    ("client_economy_data_audit.md", "economy/client_economy_data_audit.md", "Economy", []),
    ("client_progression_data_audit.md", "progression/progression_system.md", "Progression", []),
    ("client_static_table_dictionary.md", "client/static_table_dictionary.md", "Client", []),
    ("persistence_relog_audit.md", "persistence/persistence_relog_audit.md", "Persistence", []),
    ("architecture.md", "architecture/server_architecture.md", "Architecture", []),
    ("development.md", "dev/development.md", "Dev", []),
    ("network.md", "dev/network.md", "Dev", []),
    ("protocol_spec.md", "dev/protocol_spec.md", "Dev", []),
    ("bootstrap.md", "dev/bootstrap.md", "Dev", []),
    ("bootstrap_contract.md", "dev/bootstrap_contract.md", "Dev", []),
    ("startup_routing.md", "dev/startup_routing.md", "Dev", []),
    ("gameconfig_resolution.md", "dev/gameconfig_resolution.md", "Dev", []),
    ("reverse_engineering_sources.md", "dev/reverse_engineering_sources.md", "Dev", []),
    ("android_toolchain_manifest.md", "dev/android_toolchain_manifest.md", "Dev", []),
    ("all_section_battle_recovery.md", "dev/all_section_battle_recovery.md", "Dev", []),
]

HISTORY_MOVES = [
    ("2026-09-22", 1, "android_lab.md"),
    ("2026-09-22", 2, "android_lab_audit.md"),
    ("2026-09-22", 3, "first_contact_plan.md"),
    ("2026-09-22", 4, "first_contact_runs.md"),
    ("2026-09-22", 5, "milestones.md"),
    ("2026-09-22", 6, "phase6_m0_m1_report.md"),
    ("2026-09-22", 7, "phase7_m2_m3_report.md"),
    ("2026-09-22", 8, "phase8_bootstrap_first_contact_report.md"),
    ("2026-09-22", 9, "phase9_gameconfig_first_contact_report.md"),
    ("2026-09-22", 10, "phase10_android_lab_first_contact_report.md"),
    ("2026-09-22", 11, "phase11_revival_client_first_contact.md"),
    ("2026-09-22", 12, "phase12_stable_startup.md"),
    ("2026-09-23", 1, "phase13_first_contact.md"),
    ("2026-09-23", 2, "phase14_login_persistence.md"),
    ("2026-09-23", 3, "phase15_lobby_account_state.md"),
    ("2026-09-23", 4, "phase16_hero_mobility_mission.md"),
    ("2026-09-23", 5, "phase17_lobby_consistency_first_battle.md"),
    ("2026-09-23", 6, "phase18_chat_first_battle.md"),
    ("2026-09-23", 7, "phase19_economy.md"),
    ("2026-09-23", 8, "phase20_progression.md"),
    ("2026-09-23", 9, "mumu_migration.md"),
    ("2026-09-24", 1, "gold_dungeon_drop_clues.md"),
    ("2026-09-24", 2, "daily_dungeon_reward_audit.md"),
    ("2026-09-24", 3, "phase_battle_entry_domain.md"),
    ("2026-09-24", 4, "phase_test_progression_inventory.md"),
    ("2026-09-24", 5, "phase_wish_draw.md"),
    ("2026-09-24", 6, "shop_recovery_from_workbook.md"),
    ("2026-09-25", 1, "project_knowledge_index.md"),
]

SUPERSEDED_HEADERS = {
    "project_knowledge_index.md": ("SUPERSEDED", "/PROJECT_INDEX.md",
        "navigation migrated into PROJECT_INDEX.md; per-domain links now live under docs/knowledge/"),
    "drop_algorithm_reverse_engineering.md": ("CURRENT_AT_TIME", "docs/knowledge/rewards/drop_algorithm.md", ""),
    "milestones.md": ("CURRENT_AT_TIME", "", "superseded by docs/history/PROJECT_TIMELINE.md for cognitive history"),
    "runtime_coverage_matrix.md": ("CURRENT_AT_TIME", "docs/knowledge/coverage/runtime_coverage.md", ""),
}

migration = []

for domain_file, new_rel, domain, sup in KNOWLEDGE_MOVES:
    old = REPO / "docs" / domain_file
    new = REPO / "docs" / "knowledge" / new_rel
    new.parent.mkdir(parents=True, exist_ok=True)
    git("mv", old.as_posix(), new.as_posix())
    if not new.exists():
        shutil.move(str(old), str(new))
    date = time.strftime("%Y-%m-%d", time.localtime(old.stat().st_mtime)) if old.exists() else "2026-09-25"
    sup_lines = "\n".join(f"  - {s}" for s in sup) if sup else "  - (none; still authoritative)"
    header = (f"---\nDocument-Type: Current Knowledge\nDomain: {domain}\nStatus: AUTHORITATIVE\n"
              f"Updated: {date}\nSupersedes:\n{sup_lines}\n---\n\n")
    text = new.read_text(encoding="utf-8")
    if not text.startswith("---"):
        new.write_text(header + text, encoding="utf-8")
    migration.append({"old_path": f"docs/{domain_file}", "new_path": f"docs/knowledge/{new_rel}",
                      "classification": "CURRENT_KNOWLEDGE", "reason": "authoritative domain doc",
                      "canonical": f"docs/knowledge/{new_rel}", "superseded_by": "", "notes": ""})

for date, seq, old_name in HISTORY_MOVES:
    old = REPO / "docs" / old_name
    new = REPO / "docs" / "history" / f"{date}_{seq:02d}_{old_name}"
    new.parent.mkdir(parents=True, exist_ok=True)
    git("mv", old.as_posix(), new.as_posix())
    if not new.exists():
        shutil.move(str(old), str(new))
    status, sup, corr = SUPERSEDED_HEADERS.get(old_name, ("CURRENT_AT_TIME", "", ""))
    header = (f"---\nDocument-Type: Historical Report\nDate: {date}\nStatus: {status}\n"
              f"Superseded-By:\n  - {sup or '(read alongside current knowledge)'}\n"
              + (f"Known-Corrections:\n  - {corr}\n" if corr else "") + "---\n\n")
    text = new.read_text(encoding="utf-8")
    if not text.startswith("---"):
        new.write_text(header + text, encoding="utf-8")
    migration.append({"old_path": f"docs/{old_name}", "new_path": f"docs/history/{date}_{seq:02d}_{old_name}",
                      "classification": "HISTORICAL_REPORT", "reason": "phase/research report",
                      "canonical": "", "superseded_by": sup, "notes": corr})

# adr -> decisions/adr
git("mv", "docs/adr", "docs/decisions/adr")
migration.append({"old_path": "docs/adr", "new_path": "docs/decisions/adr",
                  "classification": "CURRENT_KNOWLEDGE", "reason": "decision records",
                  "canonical": "docs/decisions/adr", "superseded_by": "", "notes": ""})

# runtime evidence jsons -> evidence/raw/runtime_traces
(RI := REPO / "evidence" / "raw" / "runtime_traces").mkdir(parents=True, exist_ok=True)
for jf in ["phase12_startup_evidence.json", "phase13_first_contact_evidence.json",
           "phase14_login_persistence_evidence.json", "phase15_lobby_evidence.json"]:
    old = REPO / "docs" / jf
    if old.exists():
        git("mv", old.as_posix(), (RI / jf).as_posix())
        migration.append({"old_path": f"docs/{jf}", "new_path": f"evidence/raw/runtime_traces/{jf}",
                          "classification": "RAW_EVIDENCE", "reason": "runtime observation evidence",
                          "canonical": f"evidence/raw/runtime_traces/{jf}", "superseded_by": "", "notes": ""})

# root-level docs -> history (root is NOT a git repo: plain move)
ROOT_DOCS = [
    ("2026-09-24", 7, "deep_drop_archaeology.md"),
    ("2026-09-24", 8, "drop_graph_audit.md"),
    ("2026-09-24", 9, "dropvalue_code_path.md"),
    ("2026-09-25", 2, "external_dataset_crosscheck.md"),
]
for date, seq, name in ROOT_DOCS:
    old = ROOT / "docs" / name
    new = REPO / "docs" / "history" / f"{date}_{seq:02d}_{name}"
    new.parent.mkdir(parents=True, exist_ok=True)
    if old.exists():
        text = old.read_text(encoding="utf-8")
        header = (f"---\nDocument-Type: Historical Report\nDate: {date}\nStatus: CURRENT_AT_TIME\n"
                  f"Superseded-By:\n  - docs/knowledge/rewards/ (domain docs)\n"
                  f"Note: moved from D:/demo/x2/docs/ into the repository during knowledge reorg\n---\n\n")
        new.write_text(header + text, encoding="utf-8")
        old.unlink()
        migration.append({"old_path": f"D:/demo/x2/docs/{name}", "new_path": f"docs/history/{date}_{seq:02d}_{name}",
                          "classification": "HISTORICAL_REPORT", "reason": "root-level research report centralized",
                          "canonical": "", "superseded_by": "docs/knowledge/rewards/", "notes": "plain move (non-git root)"})
try:
    (ROOT / "docs").rmdir()
except OSError:
    pass

# snapshot of root SESSION_HANDOFF (historical) — copy, original trimmed later at root level
sh = ROOT / "SESSION_HANDOFF.md"
if sh.exists():
    snap = REPO / "docs" / "history" / "2026-09-23_10_session_handoff_phase20_snapshot.md"
    if not snap.exists():
        text = sh.read_text(encoding="utf-8")
        snap.write_text("---\nDocument-Type: Historical Report\nDate: 2026-09-23\nStatus: SUPERSEDED\n"
                        "Superseded-By:\n  - D:/demo/x2/SESSION_HANDOFF.md (trimmed current version)\n---\n\n"
                        + text, encoding="utf-8")
        migration.append({"old_path": "D:/demo/x2/SESSION_HANDOFF.md", "new_path": str(snap.relative_to(REPO)).replace("\\", "/"),
                          "classification": "HISTORICAL_REPORT", "reason": "phase20-era handoff snapshot before trim",
                          "canonical": "", "superseded_by": "D:/demo/x2/SESSION_HANDOFF.md", "notes": "copy"})

with (REPO / "analysis" / "knowledge_reorg" / "migration_map.csv").open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=["old_path", "new_path", "classification", "reason",
                                       "canonical", "superseded_by", "notes"])
    w.writeheader()
    w.writerows(migration)

print(f"migration entries: {len(migration)}")
print("docs/knowledge subdirs:", sorted(p.name for p in (REPO / "docs" / "knowledge").iterdir() if p.is_dir()))
print("history files:", len(list((REPO / "docs" / "history").glob("*.md"))))
leftover = [p.name for p in (REPO / "docs").glob("*.md")]
print("docs root leftovers:", leftover)
