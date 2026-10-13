"""Save-manager core: consistent export, transactional import, pre-import backup.

The save boundary (which tables belong to a player's archive and who owns each
row) is defined in PLAYER_TABLES / JOIN_OWNERS below and audited in
docs/savemanager/SAVE_DATA_AUDIT.md; tools/savemanager/validate_boundary.py
cross-checks the definition against the live schema so code and audit cannot
drift. The container format is specified in docs/savemanager/SAVE_FORMAT_SPEC.md.

Import treats uploaded files as untrusted input: structural, size, type and
reference validation all run before a single row is written, and the write
itself is one SQLite transaction that either lands completely or rolls back.
Table and column names used in SQL never come from the uploaded file; only
values do, and every statement is parameterized.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import sqlite3
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import validate_snapshot

SAVE_FORMAT = "X2_REVIVAL_SAVE"
SAVE_FORMAT_VERSION = 1
SERVER_SAVE_SCHEMA = "x2-revival/5"
ACCEPTED_SCHEMAS = {SERVER_SAVE_SCHEMA, "x2-revival/3", "x2-revival/4"}

MAX_UPLOAD_BYTES = 96 * 1024 * 1024
MAX_ENTRY_COUNT = 65535  # accumulated battle BLOBs; bounded by byte limits below
MAX_TOTAL_UNCOMPRESSED = 256 * 1024 * 1024
MAX_ENTRY_UNCOMPRESSED = 128 * 1024 * 1024
MAX_INT = 2 ** 62
MAX_TEXT = 32 * 1024 * 1024

SAVE_ENTRY_WHITELIST = {"manifest.json", "save.json"}
BLOB_ENTRY_RE = re.compile(r"^blobs/[A-Za-z0-9_.-]{1,120}\.bin$")

# Ownership: every persisted player-owned table. JOIN_OWNERS tables carry no
# player_id column; their rows are attributed through the parent table column
# (SAVE_DATA_AUDIT.md section 3.3): (parent_table, parent_column, child_column).
JOIN_OWNERS = {
    "world_boss_runs": ("world_boss_player_days", "boss_id", "boss_id"),
    "battle_drop_budget_versions": ("battle_entries", "uuid", "uuid"),
    "battle_receipts": ("battle_entries", "uuid", "uuid"),
    "battle_checkout_wire": ("battle_entries", "uuid", "uuid"),
    "fight_drop_items": ("fight_drop_observations", "id", "report_id"),
    "fight_drop_claims": ("fight_drop_observations", "id", "report_id"),
}
TABLES_WITH_OWNER_COLUMN = [
    "activity_events", "activity_receipts", "activity_runs", "activity_state",
    "college_alchemy_receipts", "college_job_receipts", "college_pray_receipts",
    "college_upgrade_receipts", "endless_observations", "endless_profiles",
    "endless_task_receipts", "endless_tasks", "equip_plan_receipts",
    "equipment_lock_receipts", "pending_reward_deliveries", "story_reviews",
    "world_boss_accounts", "world_boss_members", "world_boss_player_days",
    "world_boss_receipts", "world_boss_tickets",
    "achievement_events", "achievement_receipts", "achievements",
    "appearance_shop_purchases", "appearance_shop_receipts", "appearance_voice_unlock",
    "appearance_wear", "bag_jewel_seen", "bag_operation_receipts", "battle_costs",
    "battle_entries", "battle_shop_pickups", "battle_shop_purchases",
    "battle_shop_visits", "battle_unresolved_rewards", "challenge_task_state",
    "chapter_dp_floors", "chapter_dp_migrations", "chapter_objectives", "chapter_signals",
    "collection_awards", "college_state", "economy_checkouts", "economy_clears",
    "economy_events", "economy_grants", "economy_runs", "economy_tasks",
    "equipment_enhancements", "equipment_instances", "equipment_main_growth",
    "favor_touch_log", "fight_drop_observations", "gift_package_claims",
    "gift_package_daily_claims", "gift_package_receipts", "inventory",
    "item_opt_receipts", "pending_reward_instances", "pending_rewards", "player_mail",
    "progression_receipts", "reward_settlement_audit", "shop_compat_counts",
    "shop_purchase_counts", "shop_receipts", "shop_refreshes", "star_chart_receipts",
    "sweep_receipts", "task_boxes", "task_history", "task_periods",
    "wish_last_result", "wish_pity", "wish_receipts", "wish_state",
]
SEASON_ADDED_TABLES = {"season_state", "season_events", "season_receipts", "season_runs"}
WASHING_ADDED_TABLES = {"college_washing_pending", "college_washing_receipts"}
TERMINAL_WISH_ADDED_TABLES = {"favor_wish_state", "favor_wish_events", "favor_wish_receipts"}
RELEASE_ADDED_TABLES = {
    *SEASON_ADDED_TABLES,
    *WASHING_ADDED_TABLES,
    *TERMINAL_WISH_ADDED_TABLES,
    "activity_exchange_stats", "battle_element_compose", "battle_element_compose_receipts",
    "course_claims", "player_divination", "player_novice_sign", "player_total_login_claimed",
    "recharge_first", "simple_activity_claims", "simple_activity_unlocks",
}
TABLES_WITH_OWNER_COLUMN.extend(sorted(RELEASE_ADDED_TABLES))
PLAYER_TABLES = sorted(TABLES_WITH_OWNER_COLUMN) + sorted(JOIN_OWNERS)
LEGACY_PLAYER_TABLES = set(PLAYER_TABLES) - RELEASE_ADDED_TABLES
# These are server-wide encounters/calendars, not a single player's save.
GLOBAL_TABLES = {"accounts", "players", "repair_history", "world_boss_runs", "world_boss_days", "system_mail_issues", "season_calendar"}

# Global AUTOINCREMENT integer keys that may need remapping on import, with the
# referencing tables/columns. player_mail ids are always re-allocated (no DB
# references), so they are not remappable — they are simply dropped.
REMAPPABLE = {
    "equipment_instances": ("id", {
        "equipment_enhancements": ["equip_id"],
        "equipment_main_growth": ["equip_id"],
        "college_washing_pending": ["equip_id"],
        "college_washing_receipts": ["equip_id"],
        "snapshot": ["heroes[].equips[].equip_id"],
    }),
    "fight_drop_observations": ("id", {
        "fight_drop_items": ["report_id"],
        "fight_drop_claims": ["report_id"],
    }),
}
# Client-generated TEXT keys unique across the whole database.
# battle/economy run rows share one uuid family (entries, receipts, wire, costs,
# unresolved rewards, runs and the run_id references below) so a collision with
# another account's row must be remapped together to keep the joins intact.
UUID_FAMILY_COLUMNS = {
    "sweep_receipts": "request_key",
    "season_runs": "uuid", "activity_runs": "uuid", "battle_drop_budget_versions": "uuid",
    "battle_entries": "uuid", "battle_costs": "uuid",
    "battle_unresolved_rewards": "uuid", "battle_receipts": "uuid",
    "battle_checkout_wire": "uuid", "economy_runs": "uuid",
    "economy_checkouts": "uuid",
    "pending_reward_instances": "run_id", "reward_settlement_audit": "run_id",
    "battle_element_compose": "run_uuid",
}
GLOBAL_KEY_COLUMNS = {
    "season_receipts": "request_key",
    "world_boss_tickets": "ticket",
    "equip_plan_receipts": "request_key", "equipment_lock_receipts": "request_key",
    "appearance_shop_receipts": "request_key", "gift_package_receipts": "request_key",
    "item_opt_receipts": "request_key", "shop_receipts": "request_key",
}
SEQUENCED_TABLES = ("equipment_instances", "player_mail", "fight_drop_observations")
BOSS_ID_COLUMNS = {table: "boss_id" for table in
                   ("world_boss_runs", "world_boss_player_days", "world_boss_members", "world_boss_tickets")}

for _name in (*PLAYER_TABLES, *JOIN_OWNERS):
    if not re.fullmatch(r"[a-z_][a-z_0-9]*", _name):
        raise RuntimeError(f"boundary table name failed identifier check: {_name!r}")
COLUMN_NAME_RE = re.compile(r"[a-z_][a-z_0-9]*")


class SaveBoundaryError(RuntimeError):
    """A deployment added persisted tables without defining their save ownership."""


@dataclass
class ImportPlan:
    rows: dict[str, list[dict[str, Any]]]
    snapshot: dict[str, Any]
    source_player_id: int
    blobs: dict[str, bytes] = field(default_factory=dict)
    preserve_tables: set[str] = field(default_factory=set)


def _connect(store) -> sqlite3.Connection:
    db = sqlite3.connect(store.path, check_same_thread=False, timeout=30,
                         isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


class SaveManager:
    """Owns the save-management connection plus export/import logic."""

    def __init__(self, store, backup_root: Path | None = None) -> None:
        self.store = store
        self.backup_root = (Path(backup_root) if backup_root
                            else Path(store.path).parent / "server_backups" / "save_import")
        self._lock = threading.RLock()
        self.db = _connect(store)
        self._columns: dict[str, dict[str, dict[str, Any]]] = {}
        self._missing: set[str] = set()
        live = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        self._missing = {t for t in PLAYER_TABLES if t not in live}

    def close(self) -> None:
        with self._lock:
            self.db.close()

    # -- schema introspection (names from the live DB, never from files) ----

    def columns(self, table: str) -> dict[str, dict[str, Any]]:
        cached = self._columns.get(table)
        if cached is None:
            cached = {r["name"]: dict(r) for r in self.db.execute(f"PRAGMA table_info({table})")}
            self._columns[table] = cached
        return cached

    def exists(self, table: str) -> bool:
        """Boundary-table existence, refreshed lazily: services create tables
        after this manager may already have been constructed."""
        if table not in self._missing:
            return True
        row = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
        if row is not None:
            self._missing.discard(table)
        return row is not None

    # -- export -------------------------------------------------------------

    def _check_boundary(self) -> None:
        live = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        uncovered = live - set(PLAYER_TABLES) - GLOBAL_TABLES
        if uncovered:
            raise SaveBoundaryError(f"Uncovered persisted save tables: {sorted(uncovered)}")

    def export_save(self, player_id: int) -> bytes:
        """One consistent read transaction over the whole save boundary."""
        with self._lock:
            db = self.db
            db.execute("BEGIN DEFERRED")
            try:
                self._check_boundary()
                player = db.execute(
                    "SELECT id, account, login_count, snapshot FROM players WHERE id=?",
                    (player_id,)).fetchone()
                if player is None:
                    raise KeyError(player_id)
                snapshot = json.loads(player["snapshot"])
                tables: dict[str, dict[str, list[dict[str, Any]]]] = {}
                blobs: list[bytes] = []
                for table in PLAYER_TABLES:
                    tables[table] = {"rows": self._export_table(db, table, player_id, blobs)}
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
        manifest = {
            "format": SAVE_FORMAT,
            "format_version": SAVE_FORMAT_VERSION,
            "server_save_schema": SERVER_SAVE_SCHEMA,
            "exported_at": int(time.time()),
            "source_player": {"player_id": player["id"], "account": player["account"],
                              "login_count": player["login_count"]},
            "checksums": {},
        }
        save_doc = {"tables": tables, "snapshot": snapshot}
        return self._container_bytes(manifest, save_doc, blobs)

    def _export_table(self, db: sqlite3.Connection, table: str, player_id: int,
                      blobs: list[bytes]) -> list[dict[str, Any]]:
        if not self.exists(table):
            return []  # boundary table absent from this deployment: no state to export
        colnames = list(self.columns(table))
        if table in JOIN_OWNERS:
            parent, parent_col, child_col = JOIN_OWNERS[table]
            query = (f"SELECT t.* FROM {table} t JOIN {parent} p ON p.{parent_col}=t.{child_col} "
                     f"WHERE p.player_id=? ORDER BY t.rowid")
        else:
            query = f"SELECT * FROM {table} WHERE player_id=? ORDER BY rowid"
        rows: list[dict[str, Any]] = []
        for row in db.execute(query, (player_id,)):
            encoded: dict[str, Any] = {}
            for name in colnames:
                value = row[name]
                if isinstance(value, (bytes, bytearray, memoryview)):
                    encoded[name] = {"$blob": f"blobs/{len(blobs):06d}.bin"}
                    blobs.append(bytes(value))
                else:
                    encoded[name] = value
            rows.append(encoded)
        return rows

    def _container_bytes(self, manifest: dict[str, Any], save_doc: dict[str, Any],
                         blobs: list[bytes]) -> bytes:
        """Deterministic ZIP container: fixed timestamps, fixed entry order."""
        save_bytes = json.dumps(save_doc, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":"), allow_nan=False).encode("utf-8")
        checksums = {"save.json": hashlib.sha256(save_bytes).hexdigest()}
        for index, blob in enumerate(blobs):
            checksums[f"blobs/{index:06d}.bin"] = hashlib.sha256(blob).hexdigest()
        manifest = dict(manifest, checksums=checksums)
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode("utf-8")
        buffer = io.BytesIO()
        stamp = (1980, 1, 1, 0, 0, 0)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, payload in [("manifest.json", manifest_bytes), ("save.json", save_bytes)]:
                info = zipfile.ZipInfo(name, stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, payload)
            for index, blob in enumerate(blobs):
                info = zipfile.ZipInfo(f"blobs/{index:06d}.bin", stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(info, blob)
        return buffer.getvalue()

    # -- untrusted-input validation -----------------------------------------

    def parse_save(self, data: bytes) -> ImportPlan:
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise ValueError("空存档文件")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("存档文件过大")
        names: set[str] = set()
        total_uncompressed = 0
        manifest: Any = None
        save_bytes = b""
        blobs: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(bytes(data))) as zf:
            infos = zf.infolist()
            if not infos or len(infos) > MAX_ENTRY_COUNT:
                raise ValueError("ZIP 条目数超限")
            for info in infos:
                name = info.filename
                if name in names:
                    raise ValueError(f"ZIP 存在重复条目 {name!r}")
                names.add(name)
                if info.flag_bits & 0x1:
                    raise ValueError("ZIP 条目被加密")
                if name not in SAVE_ENTRY_WHITELIST and not BLOB_ENTRY_RE.match(name):
                    raise ValueError(f"ZIP 含非法条目 {name!r}")
                if info.file_size > MAX_ENTRY_UNCOMPRESSED:
                    raise ValueError(f"ZIP 条目过大 {name!r}")
                total_uncompressed += info.file_size
                if total_uncompressed > MAX_TOTAL_UNCOMPRESSED:
                    raise ValueError("ZIP 解压总量超限")
            if "manifest.json" not in names or "save.json" not in names:
                raise ValueError("存档缺少 manifest.json/save.json")
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            save_bytes = zf.read("save.json")
            for name in names:
                if name.startswith("blobs/"):
                    blobs[name] = zf.read(name)
        self._validate_manifest(manifest, blobs, save_bytes)
        save_doc = json.loads(save_bytes.decode("utf-8"))
        if not isinstance(save_doc, dict) or set(save_doc) != {"tables", "snapshot"}:
            raise ValueError("save.json 结构非法")
        if not isinstance(save_doc["snapshot"], dict):
            raise ValueError("snapshot 非法")
        try:
            validate_snapshot(save_doc["snapshot"])
        except ValueError as exc:
            raise ValueError(f"snapshot 非法: {exc}") from exc
        tables_doc = save_doc["tables"]
        if not isinstance(tables_doc, dict):
            raise ValueError('存档表集必须为对象')
        actual = set(tables_doc)
        optional = WASHING_ADDED_TABLES | TERMINAL_WISH_ADDED_TABLES
        missing = set(PLAYER_TABLES) - actual
        optional_complete = all(not (missing & group) or group <= missing
                                for group in (WASHING_ADDED_TABLES, TERMINAL_WISH_ADDED_TABLES))
        legacy = manifest['server_save_schema'] == 'x2-revival/3' and actual == LEGACY_PLAYER_TABLES
        previous = (manifest['server_save_schema'] == 'x2-revival/4'
                    and SEASON_ADDED_TABLES <= missing and missing <= SEASON_ADDED_TABLES | optional
                    and optional_complete and not (actual - set(PLAYER_TABLES)))
        pre_optional = (manifest['server_save_schema'] == SERVER_SAVE_SCHEMA
                        and missing <= optional and optional_complete and not (actual - set(PLAYER_TABLES)))
        if not legacy and not previous and not pre_optional and actual != set(PLAYER_TABLES):
            raise ValueError(f"存档表集不符 missing={sorted(missing)[:3]} extra={sorted(actual-set(PLAYER_TABLES))[:3]}")
        # Welfare claims remain protected. Task candidates and washing previews
        # absent from older exports must reset with their associated save data.
        transient = {'battle_element_compose', 'battle_element_compose_receipts'} | optional
        preserve = RELEASE_ADDED_TABLES - transient if legacy else set()
        if previous:
            preserve = set(SEASON_ADDED_TABLES)
        if legacy or previous or pre_optional:
            tables_doc.update({table: {'rows': []} for table in missing})
        source_pid = manifest["source_player"]["player_id"]
        rows_by_table: dict[str, list[dict[str, Any]]] = {}
        blob_refs: set[str] = set()
        for table in PLAYER_TABLES:
            entry = tables_doc[table]
            if not isinstance(entry, dict) or set(entry) != {"rows"}:
                raise ValueError(f"{table} 条目非法")
            rows = entry["rows"]
            if not isinstance(rows, list):
                raise ValueError(f"{table} rows 非法")
            if rows and not self.exists(table):
                raise ValueError(f"存档包含本服务器不存在的表 {table}")
            rows_by_table[table] = [self._validate_row(table, row, source_pid, blob_refs)
                                    for row in rows]
        missing_blobs = blob_refs - set(blobs)
        if missing_blobs:
            raise ValueError(f"缺失 BLOB {sorted(missing_blobs)[:3]}")
        return ImportPlan(rows=rows_by_table, snapshot=save_doc["snapshot"],
                          source_player_id=source_pid, blobs=blobs, preserve_tables=preserve)

    def _validate_manifest(self, manifest: Any, blobs: dict[str, bytes],
                           save_bytes: bytes) -> None:
        if not isinstance(manifest, dict):
            raise ValueError("manifest.json 非法")
        required = {"format", "format_version", "server_save_schema", "exported_at",
                    "source_player", "checksums"}
        if set(manifest) != required:
            raise ValueError("manifest.json 字段集不符")
        if manifest["format"] != SAVE_FORMAT:
            raise ValueError("非 X2_REVIVAL_SAVE 存档")
        if manifest["format_version"] != SAVE_FORMAT_VERSION:
            raise ValueError(f"不支持的 format_version {manifest['format_version']!r}")
        if manifest["server_save_schema"] not in ACCEPTED_SCHEMAS:
            raise ValueError(f"不支持的 server_save_schema {manifest['server_save_schema']!r}")
        if type(manifest["exported_at"]) is not int or manifest["exported_at"] < 0:
            raise ValueError("exported_at 非法")
        source = manifest["source_player"]
        if not isinstance(source, dict) or set(source) != {"player_id", "account", "login_count"}:
            raise ValueError("source_player 字段集不符")
        if type(source["player_id"]) is not int or source["player_id"] < 1:
            raise ValueError("source player_id 非法")
        if not isinstance(source["account"], str) or len(source["account"]) > 64:
            raise ValueError("source account 非法")
        if type(source["login_count"]) is not int or source["login_count"] < 0:
            raise ValueError("source login_count 非法")
        checksums = manifest["checksums"]
        if not isinstance(checksums, dict) or "save.json" not in checksums:
            raise ValueError("checksums 非法")
        if hashlib.sha256(save_bytes).hexdigest() != checksums["save.json"]:
            raise ValueError("save.json 校验和不符")
        for name, blob in blobs.items():
            expected = checksums.get(name)
            if not isinstance(expected, str) or hashlib.sha256(blob).hexdigest() != expected:
                raise ValueError(f"{name} 校验和不符")
        if set(checksums) != {"save.json"} | set(blobs):
            raise ValueError("checksums 条目与 ZIP 内容不符")

    def _validate_row(self, table: str, row: Any, source_pid: int,
                      blob_refs: set[str]) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise ValueError(f"{table} 行非法")
        schema = self.columns(table)
        unknown = set(row) - set(schema)
        if unknown:
            raise ValueError(f"{table} 行含未知列 {sorted(unknown)[:3]}")
        checked: dict[str, Any] = {}
        for name, value in row.items():
            checked[name] = self._validate_value(table, name, schema[name], value, blob_refs)
        for name, col in schema.items():
            if name not in checked and col["notnull"] and col["dflt_value"] is None:
                raise ValueError(f"{table}.{name} 缺失 NOT NULL 值")
        if "player_id" in checked and checked["player_id"] != source_pid:
            raise ValueError(f"{table} 行 player_id 与 manifest 不一致")
        return checked

    def _validate_value(self, table: str, name: str, col: dict[str, Any],
                        value: Any, blob_refs: set[str]) -> Any:
        decl = (col["type"] or "").upper()
        if isinstance(value, dict):
            if set(value) == {"$blob"} and "BLOB" in decl:
                ref = value["$blob"]
                if not isinstance(ref, str) or not BLOB_ENTRY_RE.match(ref):
                    raise ValueError(f"{table}.{name} blob 引用非法")
                blob_refs.add(ref)
                return {"$blob": ref}
            raise ValueError(f"{table}.{name} 值类型非法")
        if value is None:
            if col["notnull"]:
                raise ValueError(f"{table}.{name} 不允许为空")
            return None
        if "INT" in decl:
            if type(value) is not int:
                raise ValueError(f"{table}.{name} 应为整数")
            if not -MAX_INT <= value <= MAX_INT:
                raise ValueError(f"{table}.{name} 整数越界")
            return value
        if "TEXT" in decl or "CHAR" in decl:
            if not isinstance(value, str):
                raise ValueError(f"{table}.{name} 应为字符串")
            if len(value) > MAX_TEXT:
                raise ValueError(f"{table}.{name} 字符串过大")
            return value
        if "BLOB" in decl:
            raise ValueError(f"{table}.{name} BLOB 必须使用 $blob 编码")
        if any(tag in decl for tag in ("REAL", "FLOA", "DOUB")):
            if type(value) not in (int, float) or isinstance(value, bool):
                raise ValueError(f"{table}.{name} 应为数字")
            return value
        return value

    # -- import --------------------------------------------------------------

    def import_save(self, player_id: int, data: bytes, *, actor: str = "save-manager") -> dict[str, Any]:
        """Validate, back up the current archive, then land the new state in a
        single transaction. Any failure rolls the database back completely."""
        with self._lock:
            plan = self.parse_save(data)
            target = self.db.execute(
                "SELECT id, account FROM players WHERE id=?", (player_id,)).fetchone()
            if target is None:
                raise KeyError(player_id)
            self._validate_references(plan)
            backup_path = self._write_backup(player_id, target["account"])
            db = self.db
            db.execute("BEGIN IMMEDIATE")
            try:
                from .system_mail import remember_once_mail_history
                remember_once_mail_history(db, player_id)
                self._delete_target_state(db, player_id, plan.preserve_tables)
                uuid_map = self._compute_uuid_map(db, plan, target["id"])
                key_maps = {table: self._compute_key_map(db, table, plan, target["id"])
                            for table in GLOBAL_KEY_COLUMNS}
                existing_bosses = {r[0] for r in db.execute("SELECT boss_id FROM world_boss_runs")} if self.exists("world_boss_runs") else set()
                boss_map = {row["boss_id"]: f"imp-{player_id}-{index}-{row['boss_id']}"
                            for index, row in enumerate(plan.rows["world_boss_runs"])
                            if row["boss_id"] in existing_bosses}
                equip_map = self._insert_equipment(db, player_id, plan)
                drop_map = self._insert_drop_observations(db, player_id, plan)
                snapshot = self._remap_snapshot(plan.snapshot, equip_map)
                for table in PLAYER_TABLES:
                    if table in ("equipment_instances", "fight_drop_observations"):
                        continue
                    self._insert_rows(db, table, player_id, plan.rows[table],
                                      equip_map, drop_map, plan, uuid_map, key_maps, boss_map)
                remember_once_mail_history(db, player_id)
                db.execute("UPDATE players SET snapshot=?, revision=revision+1 WHERE id=?",
                           (json.dumps(snapshot, ensure_ascii=False, allow_nan=False,
                                       sort_keys=True), player_id))
                self._bump_sequences(db)
                if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise ValueError("导入后外键校验失败")
                counts = {t: len(plan.rows[t]) for t in PLAYER_TABLES}
                db.execute("COMMIT")
            except BaseException:
                db.execute("ROLLBACK")
                raise
            self._write_audit_log(target["account"], backup_path, plan, counts, actor)
            return {"account": target["account"], "backup": str(backup_path), "rows": counts}

    def _compute_uuid_map(self, db: sqlite3.Connection, plan: ImportPlan,
                          account_id: int) -> dict[str, str]:
        """Remap run uuids that collide with another account's surviving rows.

        The whole uuid family is remapped together so the entry/receipt/wire/run
        joins stay intact. Keys only collide across accounts (the target's own
        rows were just deleted), which is exactly the cross-account case; a
        same-account round-trip keeps every key verbatim.
        """
        existing: set[str] = set()
        for table, column in UUID_FAMILY_COLUMNS.items():
            if self.exists(table):
                existing.update(r[0] for r in db.execute(f"SELECT {column} FROM {table}"))
        incoming: set[str] = set()
        for table, column in UUID_FAMILY_COLUMNS.items():
            if self.exists(table):
                for row in plan.rows[table]:
                    value = row.get(column)
                    if isinstance(value, str):
                        incoming.add(value)
        mapping: dict[str, str] = {}
        for old in sorted(incoming):
            if old in existing:
                mapping[old] = f"imp-{account_id}-{len(mapping)}-{old}"[:300]
        return mapping

    def _compute_key_map(self, db: sqlite3.Connection, table: str, plan: ImportPlan,
                         account_id: int) -> dict[str, str]:
        if not self.exists(table):
            return {}
        column = GLOBAL_KEY_COLUMNS[table]
        existing = {r[0] for r in db.execute(f"SELECT {column} FROM {table}")}
        incoming = {row[column] for row in plan.rows[table] if isinstance(row.get(column), str)}
        return {old: f"imp-{account_id}-{index}-{old}"[:300]
                for index, old in enumerate(sorted(incoming)) if old in existing}

    def _validate_references(self, plan: ImportPlan) -> None:
        """Cross-row reference validation before touching the database."""
        entry_uuids = {row["uuid"] for row in plan.rows["battle_entries"]}
        for table in ("battle_receipts", "battle_checkout_wire", "battle_drop_budget_versions"):
            for row in plan.rows[table]:
                if row["uuid"] not in entry_uuids:
                    raise ValueError(f"{table}.uuid 引用了不存在的 battle_entries 行")
        run_ids = {row["uuid"] for row in plan.rows["economy_runs"]}
        for row in plan.rows["pending_reward_instances"]:
            if row["run_id"] not in run_ids:
                raise ValueError("pending_reward_instances.run_id 引用不存在")
        sweep_keys = {r["request_key"] for r in plan.rows["sweep_receipts"]}
        for row in plan.rows["reward_settlement_audit"]:
            if row["run_id"] not in run_ids | sweep_keys:
                raise ValueError("reward_settlement_audit.run_id 引用不存在")
        observation_ids = {row["id"] for row in plan.rows["fight_drop_observations"]}
        for table in ("fight_drop_items", "fight_drop_claims"):
            for row in plan.rows[table]:
                if row["report_id"] not in observation_ids:
                    raise ValueError(f"{table}.report_id 引用不存在")
        equip_ids = {row["id"] for row in plan.rows["equipment_instances"]}
        for table in ("equipment_enhancements", "equipment_main_growth", "college_washing_pending", "college_washing_receipts"):
            for row in plan.rows[table]:
                if row["equip_id"] not in equip_ids:
                    raise ValueError(f"{table}.equip_id 引用不存在")
        heroes = plan.snapshot.get("heroes")
        if isinstance(heroes, list):
            for hero in heroes:
                if not isinstance(hero, dict):
                    continue
                for equip in hero.get("equips") or []:
                    if isinstance(equip, dict) and type(equip.get("equip_id")) is int \
                            and equip["equip_id"] not in equip_ids:
                        raise ValueError("snapshot.heroes[].equips[].equip_id 引用不存在")

    def _write_backup(self, player_id: int, account: str) -> Path:
        """Server-side PRE_IMPORT_BACKUP; never overwrites an earlier backup."""
        current = self.export_save(player_id)
        safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", account)[:48] or f"player{player_id}"
        directory = self.backup_root / f"account_{safe_name}"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        path = directory / f"{stamp}.x2save"
        suffix = 0
        while path.exists():
            suffix += 1
            path = directory / f"{stamp}_{suffix:02d}.x2save"
        path.write_bytes(current)
        return path

    def _delete_target_state(self, db: sqlite3.Connection, player_id: int,
                             preserve_tables: set[str] | None = None) -> None:
        # Delete join-owned rows before their direct-owner parents disappear.
        for table, (parent, parent_col, child_col) in JOIN_OWNERS.items():
            if self.exists(table) and self.exists(parent):
                db.execute(f"DELETE FROM {table} WHERE {child_col} IN "
                           f"(SELECT {parent_col} FROM {parent} WHERE player_id=?)", (player_id,))
        entry_uuids = [r[0] for r in db.execute(
            "SELECT uuid FROM battle_entries WHERE player_id=?", (player_id,))]
        observation_ids = [r[0] for r in db.execute(
            "SELECT id FROM fight_drop_observations WHERE player_id=?", (player_id,))]
        for table in PLAYER_TABLES:
            if table in (preserve_tables or set()):
                continue
            if not self.exists(table):
                continue
            if table in JOIN_OWNERS:
                continue
            if table in ("battle_receipts", "battle_checkout_wire", "battle_drop_budget_versions"):
                if entry_uuids:
                    marks = ",".join("?" * len(entry_uuids))
                    db.execute(f"DELETE FROM {table} WHERE uuid IN ({marks})", entry_uuids)
                continue
            if table in ("fight_drop_items", "fight_drop_claims"):
                if observation_ids:
                    marks = ",".join("?" * len(observation_ids))
                    db.execute(f"DELETE FROM {table} WHERE report_id IN ({marks})", observation_ids)
                continue
            db.execute(f"DELETE FROM {table} WHERE player_id=?", (player_id,))

    def _insert_equipment(self, db: sqlite3.Connection, player_id: int,
                          plan: ImportPlan) -> dict[int, int]:
        rows = plan.rows["equipment_instances"]
        taken = ({r[0] for r in db.execute("SELECT id FROM equipment_instances")}
                 if self.exists("equipment_instances") else set())
        equip_map: dict[int, int] = {}
        next_id = (max(taken) if taken else 0) + 1
        for row in rows:
            old = row["id"]
            if old not in taken:
                equip_map[old] = old
            else:
                equip_map[old] = next_id
                next_id += 1
            taken.add(equip_map[old])
        for row in rows:
            values = dict(row)
            values["id"] = equip_map[values["id"]]
            values["player_id"] = player_id
            self._insert(db, "equipment_instances", values, plan)
        return equip_map

    def _insert_drop_observations(self, db: sqlite3.Connection, player_id: int,
                                  plan: ImportPlan) -> dict[int, int]:
        rows = plan.rows["fight_drop_observations"]
        taken = ({r[0] for r in db.execute("SELECT id FROM fight_drop_observations")}
                 if self.exists("fight_drop_observations") else set())
        drop_map: dict[int, int] = {}
        next_id = (max(taken) if taken else 0) + 1
        for row in rows:
            old = row["id"]
            if old not in taken:
                drop_map[old] = old
            else:
                drop_map[old] = next_id
                next_id += 1
            taken.add(drop_map[old])
        for row in rows:
            values = dict(row)
            values["id"] = drop_map[values["id"]]
            values["player_id"] = player_id
            self._insert(db, "fight_drop_observations", values, plan)
        return drop_map

    def _remap_snapshot(self, snapshot: dict[str, Any], equip_map: dict[int, int]) -> dict[str, Any]:
        if not equip_map:
            return snapshot
        heroes = snapshot.get("heroes")
        if isinstance(heroes, list):
            for hero in heroes:
                if not isinstance(hero, dict):
                    continue
                equips = hero.get("equips")
                if isinstance(equips, list):
                    for equip in equips:
                        if isinstance(equip, dict) and type(equip.get("equip_id")) is int \
                                and equip["equip_id"] in equip_map:
                            equip["equip_id"] = equip_map[equip["equip_id"]]
        return snapshot

    def _insert_rows(self, db: sqlite3.Connection, table: str, player_id: int,
                     rows: list[dict[str, Any]], equip_map: dict[int, int],
                     drop_map: dict[int, int], plan: ImportPlan,
                     uuid_map: dict[str, str] | None = None,
                     key_maps: dict[str, dict[str, str]] | None = None,
                     boss_map: dict[str, str] | None = None) -> None:
        uuid_map = uuid_map or {}
        key_maps = key_maps or {}
        for row in rows:
            values = dict(row)
            if table in BOSS_ID_COLUMNS and values.get("boss_id") in (boss_map or {}):
                values["boss_id"] = boss_map[values["boss_id"]]
            if table == "world_boss_runs" and values.get("finder") == plan.source_player_id:
                values["finder"] = player_id
            if "player_id" in self.columns(table):
                values["player_id"] = player_id
            if table in UUID_FAMILY_COLUMNS:
                column = UUID_FAMILY_COLUMNS[table]
                if isinstance(values.get(column), str) and values[column] in uuid_map:
                    values[column] = uuid_map[values[column]]
            if table in GLOBAL_KEY_COLUMNS:
                column = GLOBAL_KEY_COLUMNS[table]
                if isinstance(values.get(column), str) and values[column] in key_maps.get(table, {}):
                    values[column] = key_maps[table][values[column]]
            if table in ("equipment_enhancements", "equipment_main_growth", "college_washing_pending", "college_washing_receipts") \
                    and values.get("equip_id") in equip_map:
                values["equip_id"] = equip_map[values["equip_id"]]
            if table in ("fight_drop_items", "fight_drop_claims") \
                    and values.get("report_id") in drop_map:
                values["report_id"] = drop_map[values["report_id"]]
            if table == "player_mail":
                values.pop("id", None)  # always allocate a fresh global id
            self._insert(db, table, values, plan)

    def _insert(self, db: sqlite3.Connection, table: str, values: dict[str, Any],
                plan: ImportPlan) -> None:
        resolved = {}
        for name, value in values.items():
            if not COLUMN_NAME_RE.fullmatch(name):
                raise ValueError(f"{table} 列名非法 {name!r}")
            if isinstance(value, dict) and set(value) == {"$blob"}:
                resolved[name] = plan.blobs[value["$blob"]]
            else:
                resolved[name] = value
        names = ",".join(resolved)
        marks = ",".join("?" * len(resolved))
        db.execute(f"INSERT INTO {table} ({names}) VALUES ({marks})",
                   [resolved[c] for c in resolved])

    def _bump_sequences(self, db: sqlite3.Connection) -> None:
        for table in SEQUENCED_TABLES:
            if not self.exists(table):
                continue
            top = db.execute(f"SELECT COALESCE(MAX(id),0) FROM {table}").fetchone()[0]
            seq = db.execute("SELECT seq FROM sqlite_sequence WHERE name=?", (table,)).fetchone()
            if seq is None:
                if top:
                    db.execute("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (table, top))
            elif seq[0] < top:
                db.execute("UPDATE sqlite_sequence SET seq=? WHERE name=?", (top, table))

    def _write_audit_log(self, account: str, backup_path: Path, plan: ImportPlan,
                         counts: dict[str, int], actor: str) -> None:
        line = json.dumps({"op": "import", "actor": actor, "account": account,
                           "backup": str(backup_path), "rows": counts,
                           "source_player_id": plan.source_player_id},
                          ensure_ascii=False, sort_keys=True)
        self.backup_root.mkdir(parents=True, exist_ok=True)
        with (self.backup_root / "import_audit.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    # -- canonical state (round-trip verification) ---------------------------

    def canonical_state(self, player_id: int) -> dict[str, Any]:
        """Canonical gameplay snapshot of a player, for round-trip comparison.

        Excludes exactly the EXCLUDED_FROM_SAVE fields documented in
        SAVE_DATA_AUDIT.md (auth identity, activity counters, revision).
        Surrogate autoincrement ids are normalized to their stable business
        identity — (type_id, marker) for equipment instances, (uuid, digest)
        for drop observations — so a correct import still compares equal even
        when ids had to be remapped away from cross-account collisions.
        """
        with self._lock:
            db = self.db
            db.execute("BEGIN DEFERRED")
            try:
                player = db.execute(
                    "SELECT account, login_count, snapshot FROM players WHERE id=?",
                    (player_id,)).fetchone()
                if player is None:
                    raise KeyError(player_id)
                snapshot = json.loads(player["snapshot"])
                tables: dict[str, list[list[Any]]] = {}
                for table in PLAYER_TABLES:
                    rows = []
                    if not self.exists(table):
                        tables[table] = rows
                        continue
                    if table in JOIN_OWNERS:
                        parent, parent_col, child_col = JOIN_OWNERS[table]
                        query = (f"SELECT t.* FROM {table} t JOIN {parent} p "
                                 f"ON p.{parent_col}=t.{child_col} WHERE p.player_id=? "
                                 f"ORDER BY t.rowid")
                    else:
                        query = f"SELECT * FROM {table} WHERE player_id=? ORDER BY rowid"
                    for row in db.execute(query, (player_id,)):
                        rows.append([row[name].hex() if isinstance(row[name], bytes) else row[name]
                                     for name in row.keys()])
                    tables[table] = rows
            except BaseException:
                db.execute("ROLLBACK")
                raise
            db.execute("COMMIT")
        tables, equip_map = self._normalize_ids(tables)
        heroes = snapshot.get("heroes")
        if isinstance(heroes, list):
            for hero in heroes:
                if isinstance(hero, dict):
                    for equip in hero.get("equips") or []:
                        if isinstance(equip, dict) and type(equip.get("equip_id")) is int \
                                and equip["equip_id"] in equip_map:
                            equip["equip_id"] = equip_map[equip["equip_id"]]
        # login_count/account/created_at/revision are account identity or
        # activity fields (EXCLUDED_FROM_SAVE), never part of the comparison.
        return {"snapshot": snapshot, "tables": tables}

    def _normalize_ids(self, tables: dict[str, Any]) -> tuple[dict[str, Any], dict[int, str]]:
        def column_index(table: str, column: str) -> int:
            return list(self.columns(table)).index(column)

        equip_rows = tables["equipment_instances"]
        equip_map: dict[int, str] = {}
        idx_id = column_index("equipment_instances", "id")
        idx_type = column_index("equipment_instances", "type_id")
        idx_marker = column_index("equipment_instances", "marker")
        for row in equip_rows:
            equip_map[row[idx_id]] = f"equip:{row[idx_type]}:{row[idx_marker]}"
            row[idx_id] = equip_map[row[idx_id]]
        for table in ("equipment_enhancements", "equipment_main_growth", "college_washing_pending", "college_washing_receipts"):
            if not tables.get(table):
                continue
            index = column_index(table, "equip_id")
            for row in tables[table]:
                if isinstance(row[index], int) and row[index] in equip_map:
                    row[index] = equip_map[row[index]]
        drop_rows = tables["fight_drop_observations"]
        drop_map: dict[int, str] = {}
        idx_id = column_index("fight_drop_observations", "id")
        idx_uuid = column_index("fight_drop_observations", "uuid")
        idx_digest = column_index("fight_drop_observations", "digest")
        for row in drop_rows:
            drop_map[row[idx_id]] = f"drop:{row[idx_uuid]}:{row[idx_digest]}"
            row[idx_id] = drop_map[row[idx_id]]
        for table in ("fight_drop_items", "fight_drop_claims"):
            index = column_index(table, "report_id")
            for row in tables[table]:
                if isinstance(row[index], int) and row[index] in drop_map:
                    row[index] = drop_map[row[index]]
        mail_idx = column_index("player_mail", "id")
        for row in tables["player_mail"]:
            row[mail_idx] = None  # surrogate global id, re-allocated on import
        # the owner key itself: after a cross-account import the owner differs
        # by design; the ownership semantics are identical, so normalize it.
        for table in PLAYER_TABLES:
            schema = self.columns(table)
            if "player_id" in schema:
                index = list(schema).index("player_id")
                for row in tables[table]:
                    row[index] = None
        # Client-generated idempotency keys (uuid family / request_key) are
        # arbitrary identifiers: cross-account imports may remap them. Intern
        # every key value into a stable symbol so structural equivalence is
        # compared, not the opaque strings; one shared table keeps joins equal.
        intern: dict[str, str] = {}
        key_columns: dict[str, str] = dict(UUID_FAMILY_COLUMNS)
        key_columns.update(GLOBAL_KEY_COLUMNS)
        season_intern: dict[str, str] = {}
        for table, column in [*key_columns.items(), *BOSS_ID_COLUMNS.items()]:
            schema = self.columns(table)
            if column not in schema or not self.exists(table):
                continue
            index = list(schema).index(column)
            for row in tables[table]:
                value = row[index]
                if isinstance(value, str):
                    symbols = season_intern if table == "season_receipts" else intern
                    prefix = "#season" if table == "season_receipts" else "#k"
                    row[index] = symbols.setdefault(f"{value}", f"{prefix}{len(symbols)}")
        if self.exists("world_boss_runs"):
            index = list(self.columns("world_boss_runs")).index("finder")
            for row in tables["world_boss_runs"]:
                row[index] = None
        return tables, equip_map
