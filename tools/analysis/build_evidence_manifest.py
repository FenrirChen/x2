"""Knowledge reorg step 3: build the evidence/ layer.

- evidence/raw/... READMEs that point at the real, immutable raw evidence locations
  (large files stay in place; manifest records canonical paths + hashes).
- evidence/external/third_party/ holds the isolated third-party workbook copy.
- evidence/manifests/evidence_manifest.json with stable Evidence IDs.
- evidence/derived/README.md mapping each derived artifact to its canonical path + generator.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

REPO = Path(r"D:\demo\x2\x2_revive_workspace")
X2 = REPO.parent

EV = REPO / "evidence"
for d in ("manifests", "raw/client/il2cpp", "raw/client/metadata", "raw/client/decompiled",
          "raw/client/resources", "raw/client/apk_metadata", "raw/protocol", "raw/static_tables",
          "raw/runtime_traces", "derived", "external/third_party", "external/player_observations"):
    (EV / d).mkdir(parents=True, exist_ok=True)

def sha256(p: Path, _cache={}):
    if p in _cache:
        return _cache[p]
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    _cache[p] = h.hexdigest()
    return h.hexdigest()

def fdate(p: Path):
    return time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))

# ---------------- external workbook copy ----------------
import shutil
wb_src = X2 / "解神者本地单服-数据对照表.xlsx"
wb_dst = EV / "external/third_party/解神者本地单服-数据对照表.xlsx"
if wb_src.exists() and not wb_dst.exists():
    shutil.copyfile(wb_src, wb_dst)

# ---------------- manifest ----------------
entries = []

def add(eid, path, category, source, version, generated_by, derived_from, confidence_scope, notes, record_hash=True):
    p = Path(path)
    entry = {
        "id": eid, "path": str(p), "category": category, "source": source, "version": version,
        "exists": p.exists(), "size": p.stat().st_size if p.exists() else None,
        "hash_sha256": sha256(p) if (record_hash and p.exists() and p.is_file()) else None,
        "generated_by": generated_by, "derived_from": derived_from,
        "confidence_scope": confidence_scope, "notes": notes,
    }
    entries.append(entry)
    return entry

# RAW — client (kept at original locations; DO NOT move)
add("CLIENT_APK_REFERENCE_2_4", X2 / "X2_Eclipse_v2_4.apk", "RAW_EVIDENCE",
    "official 2.4 client (versionCode 202)", "2.4/202", "-", "-",
    "OFFICIAL_CLIENT_CONFIRMED", "Reference APK, permanently unmodified")
add("CLIENT_IL2CPP_2_4", X2 / "phase3_work/lib/arm64-v8a/libil2cpp.so", "RAW_EVIDENCE",
    "extracted from CLIENT_APK_REFERENCE_2_4", "2.4", "unzip", "CLIENT_APK_REFERENCE_2_4",
    "OFFICIAL_CLIENT_CONFIRMED", "ARM64 native code")
add("CLIENT_METADATA_2_4", X2 / "phase3_work/assets/bin/Data/Managed/Metadata/global-metadata.dat",
    "RAW_EVIDENCE", "extracted from CLIENT_APK_REFERENCE_2_4", "2.4", "unzip",
    "CLIENT_APK_REFERENCE_2_4", "OFFICIAL_CLIENT_CONFIRMED", "IL2CPP metadata")
add("CLIENT_DUMP_CS", X2 / "tools/Il2CppDumper-bin/dump.cs", "RAW_EVIDENCE",
    "Il2CppDumper over CLIENT_IL2CPP_2_4 + CLIENT_METADATA_2_4", "2.4",
    "Il2CppDumper 6.7.46", "CLIENT_IL2CPP_2_4 + CLIENT_METADATA_2_4",
    "OFFICIAL_CLIENT_CONFIRMED", "class/field/RVA dump; hash also recorded in drop_algorithm doc")
add("CLIENT_SCRIPT_JSON", X2 / "tools/Il2CppDumper-bin/script.json", "RAW_EVIDENCE",
    "Il2CppDumper", "2.4", "Il2CppDumper", "CLIENT_DUMP_CS", "OFFICIAL_CLIENT_CONFIRMED",
    "method name -> address map used by all xref tools")
add("CLIENT_STRINGLITERAL_JSON", X2 / "tools/Il2CppDumper-bin/stringliteral.json", "RAW_EVIDENCE",
    "Il2CppDumper", "2.4", "Il2CppDumper", "CLIENT_METADATA_2_4", "OFFICIAL_CLIENT_CONFIRMED", "")
add("CLIENT_UNITYSERIALIZED_2_4", X2 / "phase2_output", "RAW_EVIDENCE",
    "UnityPy scan of CLIENT_APK_REFERENCE_2_4", "2.4", "phase2_scan_bundles.py / phase2_scan_unity_data.py",
    "CLIENT_APK_REFERENCE_2_4", "OFFICIAL_CLIENT_CONFIRMED",
    "1,526 bundles + 7,934 SerializedFile object inventories")
add("CLIENT_RAW_TABLES_2_4", X2 / "phase3_output/raw_tables", "RAW_EVIDENCE",
    "decrypted table blobs from CLIENT_APK_REFERENCE_2_4", "2.4",
    "phase3_analyze.py", "CLIENT_APK_REFERENCE_2_4", "OFFICIAL_CLIENT_CONFIRMED",
    "70 raw table bins (multi-version); canonical selections recorded in phase3_active_table_versions.csv")
add("CLIENTResourceManager_REGISTRY", X2 / "analysis/drop_archaeology/resource_registry.json", "DERIVED_EVIDENCE",
    "dump of globalgamemanagers m_Container", "2.4", "analysis/drop_archaeology/dump_resource_registry.py",
    "CLIENT_APK_REFERENCE_2_4", "OFFICIAL_CLIENT_CONFIRMED",
    "10,049 registered paths; 265 table/* names")
add("CLIENT_FULL_TABLES_2_4", X2 / "analysis/drop_archaeology/full_tables", "DERIVED_EVIDENCE",
    "canonical decode of all 249 schema tables", "2.4",
    "analysis/drop_archaeology/extract_all_registered_tables.py",
    "CLIENTResourceManager_REGISTRY + CLIENT_RAW_TABLES_2_4", "OFFICIAL_CLIENT_CONFIRMED",
    "~250k records; zero record errors; canonical input for every domain analysis")
add("CLIENT_TABLE_REGISTRY_EXTRACT", X2 / "analysis/drop_archaeology/table_registry_extract.json",
    "DERIVED_EVIDENCE", "per-table parse record (265 entries)", "2.4",
    "analysis/drop_archaeology/extract_all_registered_tables.py", "CLIENTResourceManager_REGISTRY",
    "OFFICIAL_CLIENT_CONFIRMED", "")

# RAW — protocol/runtime observations
add("RUNTIME_TRACE_PHASE12_15", REPO / "evidence/raw/runtime_traces", "RAW_EVIDENCE",
    "live client-server observation during phases 12-15", "-", "manual capture",
    "-", "RUNTIME_OBSERVATION", "phase12/13/14/15 evidence jsons")

# DERIVED — repo-internal canonical artifacts (paths kept stable; generators updated)
repo_derived = [
    ("STATIC_DICTIONARY_TABLES", "analysis/static_dictionary/tables.json", "tools/analysis/build_table_dictionary.py",
     "CLIENT_FULL_TABLES_2_4 + CLIENT_DUMP_CS", "265-table data dictionary"),
    ("STATIC_DICTIONARY_DOMAINS", "analysis/static_dictionary/table_domains.json", "tools/analysis/build_table_dictionary.py",
     "STATIC_DICTIONARY_TABLES", "business-domain classification"),
    ("ID_NAMESPACES", "analysis/static_dictionary/id_namespaces.json", "tools/analysis/build_reference_graph.py",
     "CLIENT_FULL_TABLES_2_4", "30 ID domains"),
    ("REFERENCE_GRAPH", "analysis/static_dictionary/reference_graph.json", "tools/analysis/build_reference_graph.py",
     "CLIENT_FULL_TABLES_2_4", "367 CONFIRMED / 267 STRONG / 161 WEAK + 4 REJECTED"),
    ("REVERSE_REFERENCE_INDEX", "analysis/static_dictionary/reverse_reference_index.json",
     "tools/analysis/build_reference_graph.py", "REFERENCE_GRAPH", ""),
    ("PROTOCOL_CATALOG", "analysis/protocol/protocol_catalog.json", "tools/analysis/build_protocol_catalog.py",
     "CLIENT_DUMP_CS + server registry", "395 C2L / 444 L2C / 348 with send points / 47 NO_SEND_POINT"),
    ("UNHANDLED_HIGH_VALUE", "analysis/protocol/unhandled_high_value.json", "tools/analysis/build_protocol_catalog.py",
     "PROTOCOL_CATALOG", ""),
    ("SQLITE_SCHEMA_CATALOG", "analysis/persistence/sqlite_schema_catalog.json", "tools/analysis/audit_persistence.py",
     "src/x2server static parse", "24 tables"),
    ("STATE_LIFECYCLE", "analysis/persistence/state_lifecycle.json", "tools/analysis/audit_persistence.py",
     "SQLITE_SCHEMA_CATALOG", ""),
    ("SECTION_TYPE_CATALOG", "analysis/battle/section_type_catalog.json", "tools/analysis/build_section_catalog.py",
     "CLIENT_FULL_TABLES_2_4", "24 SectionTypes / 3,203 sections"),
    ("HARDCODED_BUSINESS_RULES", "analysis/coverage/hardcoded_business_rules.json", "tools/analysis/audit_hardcodes.py",
     "src/x2server + tools scan", ""),
    ("RUNTIME_COVERAGE_JSON", "analysis/coverage/runtime_coverage.json", "analysis/coverage/build_runtime_coverage.py",
     "PROTOCOL_CATALOG + audits", "76 features + static_data_reaudit block"),
    ("SECTION_REWARD_CATALOG", "analysis/reward/section_reward_catalog.json", "tools/analysis/build_section_reward_catalog.py",
     "CLIENT_FULL_TABLES_2_4", "3203/3203 classified"),
    ("REWARD_REVERSE_JSON", "analysis/reward_reverse", "tools/analysis/build_reward_reverse.py",
     "CLIENT_IL2CPP_2_4 + CLIENT_DUMP_CS", "8 evidence files for FightItemBag/Gift/Equipment/Special"),
    ("DROP_ALGORITHM_EVIDENCE", "analysis/drop_algorithm", "drop-algorithm reverse session",
     "CLIENT_IL2CPP_2_4", "CFG/callers/field_accesses/rng_calls/sample_evaluations"),
    ("DROP_GRAPH", X2 / "analysis/drop_archaeology/drop_graph.json", "analysis/drop_archaeology/build_deliverables.py",
     "CLIENT_FULL_TABLES_2_4", "332 DropProp nodes, 147 roots, closure COMPLETE"),
    ("DROPVALUE_CROSS_SCAN", X2 / "analysis/drop_archaeology/dropvalue_cross_scan.json",
     "analysis/drop_archaeology/scan_drop_ids.py", "CLIENT_FULL_TABLES_2_4",
     "341 DropValueIDs: zero hits outside sectiontable"),
    ("EXTERNAL_CROSSCHECK", X2 / "analysis/external_crosscheck", "analysis/external_crosscheck/crosscheck_*.py",
     "EXTERNAL_WORKBOOK + CLIENT_FULL_TABLES_2_4", "drop_prop_diff/shop_goods_mapping/conflicts"),
]
for eid, path, gen, frm, note in repo_derived:
    add(eid, REPO / path, "DERIVED_EVIDENCE", "script-generated", "current", gen, frm,
        "OFFICIAL_CLIENT_CONFIRMED where inputs are raw client data; see generator", note)

# EXTERNAL
add("EXTERNAL_WORKBOOK_X2_LOCAL_SERVER", wb_dst, "EXTERNAL_EVIDENCE",
    "third-party developer workbook (2026-09-25 build)", "2026-09-25", "external author",
    "-", "EXTERNAL_EVIDENCE",
    "232 sheets; drop/shop layers 99-100% consistent with CLIENT_FULL_TABLES_2_4; "
    "3 unregistered DropProp repairs and 4 MazeShop noise rows REJECTED; isolated from raw client evidence")
add("EXTERNAL_WORKBOOK_SOURCE_LOCATION", wb_src, "EXTERNAL_EVIDENCE",
    "original external location", "-", "-", "-", "EXTERNAL_EVIDENCE",
    "user-provided file also kept at D:/demo/x2/解神者本地单服-数据对照表.xlsx")

manifest = {
    "generated": time.strftime("%Y-%m-%d %H:%M"),
    "maintainer_note": "Evidence IDs are the stable way to reference evidence in docs. "
                       "Large raw artifacts stay at their original locations (recorded here); "
                       "do NOT move them. DO NOT EDIT RAW EVIDENCE MANUALLY.",
    "confidence_ladder": ["native instruction / direct xref", "static raw client data",
                          "protocol send/receive evidence", "derived reconstruction",
                          "runtime observation", "third-party independent evidence",
                          "Revival compatibility decision"],
    "entries": entries,
}
(EV / "manifests/evidence_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1),
                                                     encoding="utf-8")

# ---------------- READMEs ----------------
(EV / "README.md").write_text("""# Evidence Layer

四层知识体系的第一层：证据。分三类，禁止互相混合。

- **raw/** — 官方 2.4 客户端直接产物 + 运行时观测。**DO NOT EDIT MANUALLY**。
  大文件（APK/libil2cpp.so/global-metadata.dat/解包目录）保留在原始位置，由
  `manifests/evidence_manifest.json` 登记真实路径与 SHA256，不复制、不搬动。
- **derived/** — 由脚本从 raw 可再生成的机器可读分析。canonical 路径登记在 manifest；
  每个产物必须能用 `tools/analysis/` 的生成器重跑。
- **external/** — 第三方资料（隔离，永不与 raw 混放）。`external/third_party/` 存放
  《解神者本地单服-数据对照表.xlsx》副本；`external/player_observations/` 存放玩家实测
  （如随机商店 22 条，见 external_crosscheck 报告）。

引用规范：文档里引用证据请用 Evidence ID（如 `CLIENT_IL2CPP_2_4`、`DROP_GRAPH`），
不要写"之前那个 json"。新增证据时运行 `tools/analysis/build_evidence_manifest.py` 重新登记。
""", encoding="utf-8")

(EV / "raw/client/README.md").write_text("""# Raw Client Evidence（实际位置索引）

| Evidence ID | 实际路径 | 说明 |
|---|---|---|
| CLIENT_APK_REFERENCE_2_4 | `D:/demo/x2/X2_Eclipse_v2_4.apk` | Reference APK，永久原样 |
| CLIENT_IL2CPP_2_4 | `D:/demo/x2/phase3_work/lib/arm64-v8a/libil2cpp.so` | ARM64 原生代码 |
| CLIENT_METADATA_2_4 | `D:/demo/x2/phase3_work/assets/bin/Data/Managed/Metadata/global-metadata.dat` | IL2CPP metadata |
| CLIENT_DUMP_CS | `D:/demo/x2/tools/Il2CppDumper-bin/dump.cs`（含 script.json/stringliteral.json） | 类/字段/RVA dump |
| CLIENT_UNITYSERIALIZED_2_4 | `D:/demo/x2/phase2_output/` | 1,526 bundle + 7,934 SerializedFile 清单 |
| CLIENT_RAW_TABLES_2_4 | `D:/demo/x2/phase3_output/raw_tables/` | 70 个解密表 blob（多版本） |

运行时观测 trace 在 `evidence/raw/runtime_traces/`。
以上路径不搬动：多个 xref/解析工具以这些绝对位置为准。
""", encoding="utf-8")

(EV / "derived/README.md").write_text("""# Derived Evidence（canonical 索引）

| Evidence ID | canonical 路径（相对仓库根） | 生成器 |
|---|---|---|
| STATIC_DICTIONARY_TABLES / _DOMAINS | `analysis/static_dictionary/` | tools/analysis/build_table_dictionary.py |
| ID_NAMESPACES / REFERENCE_GRAPH / REVERSE_REFERENCE_INDEX | `analysis/static_dictionary/` | tools/analysis/build_reference_graph.py |
| PROTOCOL_CATALOG / UNHANDLED_HIGH_VALUE | `analysis/protocol/` | tools/analysis/build_protocol_catalog.py |
| SQLITE_SCHEMA_CATALOG / STATE_LIFECYCLE | `analysis/persistence/` | tools/analysis/audit_persistence.py |
| SECTION_TYPE_CATALOG | `analysis/battle/` | tools/analysis/build_section_catalog.py |
| HARDCODED_BUSINESS_RULES / RUNTIME_COVERAGE_JSON | `analysis/coverage/` | tools/analysis/audit_hardcodes.py、analysis/coverage/build_runtime_coverage.py、tools/analysis/build_coverage_reaudit.py |
| SECTION_REWARD_CATALOG | `analysis/reward/` | tools/analysis/build_section_reward_catalog.py |
| REWARD_REVERSE_JSON | `analysis/reward_reverse/` | tools/analysis/build_reward_reverse.py |
| DROP_ALGORITHM_EVIDENCE | `analysis/drop_algorithm/` | drop-algorithm 逆向会话（CFG/callers/rng） |
| DROP_GRAPH / DROPVALUE_CROSS_SCAN / CLIENT_FULL_TABLES_2_4 / EXTERNAL_CROSSCHECK | `D:/demo/x2/analysis/drop_archaeology/`、`D:/demo/x2/analysis/external_crosscheck/` | 同目录脚本 |

同一产物只有一个 canonical；历史版本进 `docs/history/` 或 `docs/archive/superseded/`。
重跑生成器不会改变路径。
""", encoding="utf-8")

(EV / "external/README.md").write_text("""# External Evidence（隔离区）

- `third_party/解神者本地单服-数据对照表.xlsx` — 第三方开发者工作簿（Evidence ID:
  EXTERNAL_WORKBOOK_X2_LOCAL_SERVER）。交叉验证结论见 `docs/history/2026-09-25_02_external_dataset_crosscheck.md`
  摘要：掉落/商店静态层 99–100% 与我方 APK 解码一致；3 处未申报 DropProp 修复与 4 处 MazeShop
  噪声行不采纳；其"随机商店(实测)"22 条为玩家实测（player observation）。
- 禁止把本目录内容当作官方客户端证据引用。
""", encoding="utf-8")

print("evidence entries:", len(entries))
print("manifest written; external workbook copied:", wb_dst.exists())
