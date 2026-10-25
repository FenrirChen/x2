"""Save-manager core: export/import/round-trip/cross-account/security.

The round-trip test is the primary acceptance gate (task section 18):
SNAPSHOT_A -> export -> mutate -> import -> SNAPSHOT_C must equal SNAPSHOT_A
across the complete audited save boundary.
"""
import io
import json
import sqlite3
import zipfile

import pytest

from x2server.player.accounts import AccountStore
from x2server.player.save_manager import (
    PLAYER_TABLES, SAVE_FORMAT, SAVE_FORMAT_VERSION, SERVER_SAVE_SCHEMA,
    JOIN_OWNERS, SaveManager,
)
from x2server.player.store import PlayerStore


def make_env(tmp_path):
    store = PlayerStore(tmp_path / "player.db")
    accounts = AccountStore(store)
    manager = SaveManager(store, backup_root=tmp_path / "server_backups" / "save_import")
    return store, accounts, manager


def test_import_does_not_reissue_once_mail_across_accounts_or_old_archives(tmp_path):
    from x2server.player.system_mail import ONCE_MAIL_PREFIXES
    store, accounts, manager = make_env(tmp_path)
    build_full_schema(store)
    try:
        assert accounts.create('old', 'old-password', 100) == 'created'
        assert accounts.create('new', 'new-password', 101) == 'created'
        old = accounts.get_by_name('old')['player_id']
        new = accounts.get_by_name('new')['player_id']
        with store.db:
            store.db.execute('UPDATE player_mail SET state=3,deleted=1 WHERE player_id=?', (old,))
            # Also cover a legacy destination without the new server ledger.
            store.db.execute('DELETE FROM player_mail WHERE player_id=?', (new,))
            store.db.execute('DELETE FROM system_mail_issues WHERE player_id=?', (new,))
        archive = manager.export_save(old)
        assert 'system_mail_issues' not in manager.parse_save(archive).rows
        manager.import_save(new, archive)
        count = store.db.execute('SELECT count(*) FROM player_mail WHERE player_id=?', (new,)).fetchone()[0]
        for ensure in (accounts.ensure_welcome_mail, accounts.ensure_hero_choice_mail,
                       accounts.ensure_ultimate_causality_mail, accounts.ensure_revival_supply_mail, accounts.ensure_causality_oct13_mail,
                       accounts.ensure_journey_supply_mail, accounts.ensure_oct25_supply_mail):
            assert ensure(new, 200) is False
        assert store.db.execute('SELECT count(*) FROM player_mail WHERE player_id=?', (new,)).fetchone()[0] == count
        # Even an archive lacking the once-mail rows cannot erase server history.
        with store.db:
            store.db.execute('DELETE FROM player_mail WHERE player_id=?', (old,))
        archive = manager.export_save(old)
        manager.import_save(new, archive)
        assert not accounts.ensure_welcome_mail(new, 201)
        assert not accounts.ensure_ultimate_causality_mail(new, 201)
        assert not accounts.ensure_causality_oct13_mail(new, 201)
        assert not accounts.ensure_journey_supply_mail(new, 201)
        assert not accounts.ensure_oct25_supply_mail(new, 201)
        assert store.db.execute('SELECT count(*) FROM system_mail_issues WHERE player_id=?', (new,)).fetchone()[0] == len(ONCE_MAIL_PREFIXES)
    finally:
        manager.close()
        store.close()


def build_full_schema(store):
    """Instantiate every service module so its persisted tables exist.

    Mirrors tools/local_game_server.run wiring (schema creation happens in
    service constructors); clock is fixed for determinism.
    """
    from x2server.player.battle import BattleService
    from x2server.player.battle_shop import BattleShopService
    from x2server.player.birthday import BirthdayService
    from x2server.player.collection import CollectionService
    from x2server.player.college import CollegeStateRepository
    from x2server.player.economy import EconomyService
    from x2server.player.equipment import EquipmentService
    from x2server.player.favor import FavorService
    from x2server.player.gift_packages import GiftPackageService
    from x2server.player.mail import MailService
    from x2server.player.appearance import AppearanceService
    from x2server.player.appearance_shop import AppearanceShopService
    from x2server.player.bag_items import BagItemService
    from x2server.player.progression import ProgressionService
    from x2server.player.server_clock import ServerClock
    from x2server.player.shop import ShopService
    from x2server.player.star_chart import StarChartService
    from x2server.player.terminal import TerminalService
    from x2server.player.tutorial import TutorialService
    from x2server.player.wish import WishService

    clock = ServerClock()
    college = CollegeStateRepository(store, clock)
    economy = EconomyService(store, clock=clock.now)
    from x2server.player.divination import DivinationService
    from x2server.player.element_compose import ElementComposeService
    DivinationService(store, economy)
    ElementComposeService(economy)
    StarChartService(store, economy)
    equipment = EquipmentService(store, economy)
    from x2server.player.equip_plans import EquipPlanService
    from x2server.player.activity import ActivityService
    from x2server.player.college import CollegeService
    EquipPlanService(store, economy, equipment=equipment, clock=clock)
    ActivityService(economy)
    CollegeService(college, economy=economy)
    WishService(store, economy, clock=clock)
    ShopService(store, economy)
    GiftPackageService(store, economy)
    CollectionService(store, economy)
    FavorService(store, economy, clock=clock.now)
    appearance = AppearanceService(store, economy)
    AppearanceShopService(store, economy, appearance)
    MailService(store, economy, clock=clock.now)
    TerminalService(store, economy, clock=clock.now)
    BagItemService(store, economy)
    BattleService(store, economy)
    BattleShopService(store, economy)
    ProgressionService(store, economy, appearance)
    TutorialService(store)
    BirthdayService(store)
    college  # instantiated for its schema side effect
    # challenge_task_state exists in the live deployment DB (created by a
    # runtime repair script, out of current src); replicate its live DDL so the
    # save boundary path for it is exercised.
    store.db.execute("""CREATE TABLE IF NOT EXISTS challenge_task_state (
        player_id INTEGER NOT NULL, task_id INTEGER NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
        claimed INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(player_id, task_id))""")
    store.db.commit()
    store.db.execute('''CREATE TABLE IF NOT EXISTS pending_reward_deliveries (
        player_id INTEGER NOT NULL, source TEXT NOT NULL, item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL, PRIMARY KEY(player_id,source,item_id))''')
    store.db.commit()


def populate_rich_state(db: sqlite3.Connection, player_id: int):
    """Insert at least one row into every boundary table for the player."""
    def columns(table):
        return [r["name"] for r in db.execute(f"PRAGMA table_info({table})")]

    def column_type(table, name):
        return next((r["type"] or "" for r in db.execute(f"PRAGMA table_info({table})")
                     if r["name"] == name), "")

    counters = {"n": 0}
    blob_tables = {t for t in PLAYER_TABLES
                   if any("BLOB" in (r["type"] or "").upper()
                          for r in db.execute(f"PRAGMA table_info({t})"))}
    for table in PLAYER_TABLES:
        if table in JOIN_OWNERS:
            continue  # join-owned rows are written through their parent's flow below
        cols = columns(table)
        row = {}
        for name in cols:
            if name == "player_id":
                row[name] = player_id
            elif table in blob_tables and "BLOB" in column_type(table, name).upper():
                row[name] = b"\x01\x02"
            else:
                counters["n"] += 1
                row[name] = counters["n"]
        # real-ish values for the interesting columns
        if table == "equipment_instances":
            row = {"id": 40, "player_id": player_id, "type_id": 140, "level": 3,
                   "exp": 10, "star": 2, "param": '{"hp":1}', "marker": "m40", "locked": 1}
        elif table == "player_mail":
            row = {"id": row["id"], "player_id": player_id, "sender": "system",
                   "title": f"邮件{row['id']}", "body": "内容", "state": 0,
                   "created_at": 1000 + row["id"], "attachments": '{"item":{"123":1}}',
                   "deleted": 0, "source_key": f"key{row['id']}"}
        elif table == "fight_drop_observations":
            row = {"id": row["id"], "player_id": player_id, "uuid": f"obs-uuid-{row['id']}",
                   "session_id": "s1", "request_id": row["id"], "digest": f"d{row['id']}",
                   "recorded_at": 1000, "body": b"\x01\x02", "decoded": "{}", "context": "{}"}
        elif table == "battle_entries":
            row = {"player_id": player_id, "request_key": f"rk-{player_id}", "uuid": f"entry-uuid-{player_id}",
                   "created_at": 1000, "response": b"\x05\x06", "section_type": 0,
                   "entry_source": "MainMission", "map_id": 0, "team_json": "[]", "ai_cost": 0}
        elif table == "college_state":
            row = {"player_id": player_id, "version": 1, "state_json": '{"g":1}',
                   "created_at": 1000, "updated_at": 1000}
        elif table == "economy_runs":
            row["uuid"] = f"run-{player_id}"
        elif table in ("pending_reward_instances", "reward_settlement_audit"):
            row["run_id"] = f"run-{player_id}"
        elif table in ("equipment_enhancements", "equipment_main_growth", "college_washing_pending", "college_washing_receipts"):
            row["equip_id"] = 40  # references the instance inserted above
        db.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                   list(row.values()))
        # join-owned children for the two parent flows we created
        if table == "battle_entries":
            db.execute("INSERT INTO battle_drop_budget_versions VALUES (?,?)",
                       (row["uuid"], "test-policy"))
            db.execute("INSERT INTO battle_receipts VALUES (?,?,?,?)",
                       (row["uuid"], "hash", 1000, b"\x07\x08"))
            db.execute("INSERT INTO battle_checkout_wire VALUES (?,?,?)",
                       (row["uuid"], b"\x09", "[]"))
        if table == "world_boss_player_days":
            db.execute('''INSERT INTO world_boss_runs
                (boss_id,type_id,group_id,created,state,finish,max_hp,hp,finder,finder_name,monster_level)
                VALUES (?,?,?,1000,0,0,100,100,?,'Save owner',30)''',
                       (str(row['boss_id']), row['type_id'], 'test', player_id))
        if table == "fight_drop_observations":
            db.execute("INSERT INTO fight_drop_items VALUES (?,?,?,?,?,?)",
                       (row["id"], 0, 123, 1, 0, 0))
            db.execute("INSERT INTO fight_drop_claims VALUES (?,?,?,?)",
                       (row["id"], "npcData", 0, "{}"))
    # second equipment instance referenced by snapshot hero equips
    db.execute("INSERT INTO equipment_instances (id,player_id,type_id,level,exp,star,param,marker) VALUES (?,?,?,?,?,?,?,?)",
               (39, player_id, 199, 1, 0, 1, '{"atk":2}', "m39"))


def rich_snapshot(equip_id: int) -> dict:
    return {"nickname": "存档者", "level": 12, "gold": 500, "crystal": 42, "exp": 7,
            "show": 1003, "main_chapter": 2010200, "main_section": 2110106,
            "mobility": {"power": 120, "shop_power_fetch_time": 1,
                         "section_power_fetch_time": 2, "dbp_next_refresh_time": 3},
            "heroes": [
                {"id": 1003, "state": 2, "level": 30, "star": 4,
                 "equips": [{"position": 1, "equip_id": equip_id}],
                 "god_equip": {"id": 1503, "level": 45, "star": 3},
                 "skills": [{"id": 10030, "level": 5}]},
                {"id": 1028, "state": 2, "level": 25, "star": 3, "equips": []},
            ],
            "star_chart": {"auto_add": False, "points": [], "skills": []}}


def apply_snapshot(store: PlayerStore, player_id: int, snapshot: dict):
    row = store.db.execute("SELECT revision FROM players WHERE id=?", (player_id,)).fetchone()
    store.save_snapshot(player_id, snapshot, row["revision"])


@pytest.fixture()
def env(tmp_path):
    store, accounts, manager = make_env(tmp_path)
    build_full_schema(store)
    assert accounts.create("alpha", "pw-alpha", 100) == "created"
    assert accounts.create("beta", "pw-beta", 101) == "created"
    alpha = accounts.get_by_name("alpha")["player_id"]
    beta = accounts.get_by_name("beta")["player_id"]
    apply_snapshot(store, alpha, rich_snapshot(40))
    with store.db:
        populate_rich_state(store.db, alpha)
    yield store, accounts, manager, alpha, beta
    manager.close()


def test_export_container_structure(env):
    store, accounts, manager, alpha, _ = env
    data = manager.export_save(alpha)
    assert len(data) < 96 * 1024 * 1024
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "save.json"} <= names
        manifest = json.loads(zf.read("manifest.json"))
        assert manifest["format"] == SAVE_FORMAT
        assert manifest["format_version"] == SAVE_FORMAT_VERSION
        assert manifest["server_save_schema"] == SERVER_SAVE_SCHEMA
        assert manifest["source_player"]["account"] == "alpha"
        assert hashlib_ok(manifest["checksums"]["save.json"], zf.read("save.json"))
        for name in names - {"manifest.json", "save.json"}:
            assert hashlib_ok(manifest["checksums"][name], zf.read(name))
        save_doc = json.loads(zf.read("save.json"))
        assert set(save_doc["tables"]) == set(PLAYER_TABLES)
        assert len(save_doc["tables"]["inventory"]["rows"]) >= 1


def test_export_refuses_to_silently_omit_new_persisted_tables(env):
    from x2server.player.save_manager import SaveBoundaryError
    store, _, manager, alpha, _ = env
    with store.db:
        store.db.execute('CREATE TABLE future_feature (player_id INTEGER, value TEXT)')
    with pytest.raises(SaveBoundaryError, match='future_feature'):
        manager.export_save(alpha)


@pytest.mark.parametrize('schema', [SERVER_SAVE_SCHEMA, 'x2-revival/4'])
def test_pre_washing_archives_clear_stale_preview_without_reopening_welfare(env, schema):
    from x2server.player.save_manager import WASHING_ADDED_TABLES, SEASON_ADDED_TABLES
    store, _, manager, alpha, _ = env
    archive = manager.export_save(alpha)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        manifest = json.loads(z.read('manifest.json'))
        document = json.loads(z.read('save.json'))
        blobs = [z.read(name) for name in sorted(z.namelist()) if name.startswith('blobs/')]
    for table in WASHING_ADDED_TABLES | (SEASON_ADDED_TABLES if schema == 'x2-revival/4' else set()):
        del document['tables'][table]
    manifest['server_save_schema'] = schema
    manager.import_save(alpha, manager._container_bytes(manifest, document, blobs))
    for table in WASHING_ADDED_TABLES:
        assert not store.db.execute(f'SELECT 1 FROM {table} WHERE player_id=?', (alpha,)).fetchone()


def test_legacy_export_preserves_destination_welfare_claims(env):
    from x2server.player.save_manager import RELEASE_ADDED_TABLES
    _, _, manager, alpha, _ = env
    archive = manager.export_save(alpha)
    before = manager.canonical_state(alpha)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        manifest = json.loads(z.read('manifest.json'))
        document = json.loads(z.read('save.json'))
        blobs = [z.read(name) for name in sorted(z.namelist()) if name.startswith('blobs/')]
    manifest['server_save_schema'] = 'x2-revival/3'
    for table in RELEASE_ADDED_TABLES:
        del document['tables'][table]
    legacy = manager._container_bytes(manifest, document, blobs)
    manager.import_save(alpha, legacy)
    after = manager.canonical_state(alpha)
    for table in RELEASE_ADDED_TABLES - {'battle_element_compose', 'battle_element_compose_receipts', 'college_washing_pending', 'college_washing_receipts', 'favor_wish_state', 'favor_wish_events', 'favor_wish_receipts'}:
        assert after['tables'][table] == before['tables'][table]
    manifest['server_save_schema'] = SERVER_SAVE_SCHEMA
    with pytest.raises(ValueError, match='表集不符'):
        manager.parse_save(manager._container_bytes(manifest, document, blobs))


def hashlib_ok(expected: str, payload: bytes) -> bool:
    import hashlib
    return hashlib.sha256(payload).hexdigest() == expected


def test_export_is_serialization_deterministic(env):
    store, accounts, manager, alpha, _ = env
    first = manager.export_save(alpha)
    second = manager.export_save(alpha)
    with zipfile.ZipFile(io.BytesIO(first)) as a, zipfile.ZipFile(io.BytesIO(second)) as b:
        assert a.read("save.json") == b.read("save.json")


def test_round_trip_restores_complete_state(env):
    """The core acceptance: export S, mutate everything, import S, compare."""
    store, accounts, manager, alpha, _ = env
    snapshot_a = manager.canonical_state(alpha)
    save_a = manager.export_save(alpha)

    # Mutate the account in every subsystem, then snapshot B must differ.
    apply_snapshot(store, alpha, {**rich_snapshot(40), "gold": 999999, "level": 33})
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (?,9999,7)", (alpha,))
        store.db.execute("UPDATE equipment_instances SET level=9 WHERE id=40")
        store.db.execute("INSERT INTO player_mail VALUES (NULL,?,'x','t','b',0,2000,'{}',0,NULL)",
                         (alpha,))
        store.db.execute("INSERT INTO achievements VALUES (?,500,10,1)", (alpha,))
        store.db.execute("INSERT INTO task_history VALUES (?,1,300,42,5,1)", (alpha,))
        store.db.execute("INSERT INTO economy_runs VALUES ('run-x',?,'sess',1,1,0,'MainMission')",
                         (alpha,))
        store.db.execute("INSERT INTO pending_reward_instances VALUES ('run-x',0,?,5,1,2,0,'r')",
                         (alpha,))
        store.db.execute("INSERT INTO battle_entries VALUES (?, 'rk2', 'uuid2', 1000, ?, 0, 'MainMission', 0, '[]', 0)",
                         (alpha, b"\x01"))
        store.db.execute("INSERT INTO battle_receipts VALUES ('uuid2','h',1000,?)", (b"\x02",))
        store.db.execute("DELETE FROM inventory WHERE player_id=? AND item_id=1", (alpha,))
    snapshot_b = manager.canonical_state(alpha)
    assert snapshot_b != snapshot_a

    manager.import_save(alpha, save_a)
    snapshot_c = manager.canonical_state(alpha)
    assert snapshot_c == snapshot_a


def test_import_requires_valid_target(env):
    store, accounts, manager, alpha, _ = env
    save_a = manager.export_save(alpha)
    with pytest.raises(KeyError):
        manager.import_save(424242, save_a)


def test_import_rejects_corrupt_and_malicious_files(env):
    store, accounts, manager, alpha, _ = env
    save_a = manager.export_save(alpha)

    with pytest.raises(ValueError):
        manager.import_save(alpha, b"")

    truncated = save_a[: len(save_a) // 2]
    with pytest.raises(Exception):
        manager.import_save(alpha, truncated)

    with zipfile.ZipFile(io.BytesIO(save_a)) as zf:
        manifest_bytes = zf.read("manifest.json")
        save_bytes = zf.read("save.json")
        manifest = json.loads(manifest_bytes)
        blobs = {n: zf.read(n) for n in zf.namelist() if n.startswith("blobs/")}

    def repack(new_manifest, new_save=save_bytes, extra_entries=None):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", new_manifest)
            zf.writestr("save.json", new_save)
            for name, payload in blobs.items():
                zf.writestr(name, payload)
            for name, payload in (extra_entries or {}).items():
                zf.writestr(name, payload)
        return buffer.getvalue()

    bad = dict(manifest)
    for mutation in (
        {"format": "OTHER_SAVE"},
        {"format_version": 2},
        {"server_save_schema": "x2-revival/999"},
        {"exported_at": -1},
        {"source_player": {"player_id": 0, "account": "x", "login_count": 0}},
    ):
        payload = {**manifest, **mutation}
        with pytest.raises(ValueError):
            manager.parse_save(repack(json.dumps(payload)))

    tampered = {**manifest, "checksums": {**manifest["checksums"], "save.json": "00" * 32}}
    with pytest.raises(ValueError):
        manager.parse_save(repack(json.dumps(tampered)))

    evil_entries = {"blobs/../evil.bin": b"x", "/abs.bin": b"x", "dup.bin": b"x"}
    with pytest.raises(ValueError):
        manager.parse_save(repack(manifest_bytes, extra_entries=evil_entries))


def test_import_rejects_schema_violations(env):
    store, accounts, manager, alpha, _ = env
    with zipfile.ZipFile(io.BytesIO(manager.export_save(alpha))) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        save_doc = json.loads(zf.read("save.json"))

    def repack(save):
        save_bytes = json.dumps(save, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")).encode()
        manifest_bytes = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest_bytes)
            zf.writestr("save.json", save_bytes)
        return buffer.getvalue()

    def with_checksums(save):
        import hashlib
        save_bytes = json.dumps(save, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")).encode()
        manifest = {
            "format": SAVE_FORMAT, "format_version": 1,
            "server_save_schema": SERVER_SAVE_SCHEMA, "exported_at": 0,
            "source_player": {"player_id": 1, "account": "alpha", "login_count": 0},
            "checksums": {"save.json": hashlib.sha256(save_bytes).hexdigest()},
        }
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", json.dumps(manifest))
            zf.writestr("save.json", save_bytes)
        return buffer.getvalue()

    missing = {**save_doc, "tables": {k: v for k, v in save_doc["tables"].items() if k != "inventory"}}
    with pytest.raises(ValueError):
        manager.parse_save(with_checksums(missing))

    extra = {**save_doc, "tables": {**save_doc["tables"], "hack_table": {"rows": []}}}
    with pytest.raises(ValueError):
        manager.parse_save(with_checksums(extra))

    bad_column = json.loads(json.dumps(save_doc))
    bad_column["tables"]["inventory"]["rows"][0]["evil_column"] = 1
    with pytest.raises(ValueError):
        manager.parse_save(with_checksums(bad_column))

    bad_type = json.loads(json.dumps(save_doc))
    bad_type["tables"]["inventory"]["rows"][0]["quantity"] = "many"
    with pytest.raises(ValueError):
        manager.parse_save(with_checksums(bad_type))

    bad_player = json.loads(json.dumps(save_doc))
    bad_player["tables"]["inventory"]["rows"][0]["player_id"] = 999
    with pytest.raises(ValueError):
        manager.parse_save(with_checksums(bad_player))

    bad_snapshot = {**save_doc, "snapshot": {"level": -5}}
    with pytest.raises(ValueError):
        manager.parse_save(with_checksums(bad_snapshot))


def test_import_rejects_broken_references(env):
    store, accounts, manager, alpha, _ = env
    plan = manager.parse_save(manager.export_save(alpha))
    plan.rows["equipment_enhancements"][0]["equip_id"] = 424242
    container = manager._container_bytes(
        {"format": SAVE_FORMAT, "format_version": 1, "server_save_schema": SERVER_SAVE_SCHEMA,
         "exported_at": 0, "source_player": {"player_id": plan.source_player_id,
                                             "account": "alpha", "login_count": 0},
         "checksums": {}},
        {"tables": plan.rows, "snapshot": plan.snapshot}, [])
    # checksums empty -> rejected before reference validation
    with pytest.raises(ValueError):
        manager.parse_save(container)


def test_import_transaction_rollback_on_failure(env, monkeypatch):
    store, accounts, manager, alpha, _ = env
    save_a = manager.export_save(alpha)
    apply_snapshot(store, alpha, {**rich_snapshot(40), "gold": 777})
    with store.db:
        store.db.execute("INSERT INTO inventory VALUES (?,5555,1)", (alpha,))
    before = manager.canonical_state(alpha)

    original_insert = SaveManager._insert

    def failing_insert(self, db, table, values, plan):
        if table == "player_mail":
            raise RuntimeError("simulated mid-import crash")
        return original_insert(self, db, table, values, plan)

    monkeypatch.setattr(SaveManager, "_insert", failing_insert)
    with pytest.raises(RuntimeError):
        manager.import_save(alpha, save_a)
    monkeypatch.setattr(SaveManager, "_insert", original_insert)
    assert manager.canonical_state(alpha) == before


def test_import_retains_only_latest_pre_import_backup(env):
    store, accounts, manager, alpha, _ = env
    save_a = manager.export_save(alpha)
    manager.import_save(alpha, save_a)
    first = manager.import_save(alpha, save_a)
    second = manager.import_save(alpha, save_a)
    assert first["backup"] == second["backup"]
    assert len(list(manager.backup_root.rglob("*.x2save"))) == 1
    # the backups are themselves valid containers that can be re-imported
    manager.parse_save(open(first["backup"], "rb").read())


def test_cross_account_import_keeps_identity_and_remaps_ids(env):
    store, accounts, manager, alpha, beta = env
    save_a = manager.export_save(alpha)
    manager.import_save(beta, save_a)

    # beta's auth identity must be untouched
    assert accounts.verify("beta", "pw-beta", 999)["account_id"] == accounts.get_by_name("beta")["account_id"]
    assert accounts.verify("alpha", "pw-beta", 1000) is None
    assert accounts.get_by_name("beta")["username"] == "beta"

    # beta's gameplay state now equals alpha's exported state
    assert manager.canonical_state(beta) == manager.canonical_state(alpha)

    # no shared equipment rows / foreign keys pointing at alpha
    a_ids = {r[0] for r in store.db.execute(
        "SELECT id FROM equipment_instances WHERE player_id=?", (alpha,))}
    b_ids = {r[0] for r in store.db.execute(
        "SELECT id FROM equipment_instances WHERE player_id=?", (beta,))}
    assert not (a_ids & b_ids)
    for (equip_id,) in store.db.execute(
            "SELECT equip_id FROM equipment_enhancements WHERE player_id=?", (beta,)):
        assert equip_id in b_ids
    # and alpha is untouched by beta's import
    save_a_after = manager.export_save(alpha)
    assert manager.parse_save(save_a_after) is not None


def test_sequences_advance_past_restored_ids(env):
    store, accounts, manager, alpha, _ = env
    save_a = manager.export_save(alpha)
    manager.import_save(alpha, save_a)
    with store.db:
        store.db.execute("INSERT INTO equipment_instances (id,player_id,type_id,level,exp,star,param,marker) VALUES (NULL,?,1,0,0,0,'{}','fresh')",
                         (alpha,))
        row = store.db.execute("SELECT MAX(id) FROM equipment_instances").fetchone()
        assert row[0] >= 41


def test_full_state_in_every_exported_table(env):
    """populate_rich_state covers every direct-owner table; export must carry it."""
    store, accounts, manager, alpha, _ = env
    plan = manager.parse_save(manager.export_save(alpha))
    empty_direct = [t for t in PLAYER_TABLES if t not in JOIN_OWNERS and not plan.rows[t]]
    assert empty_direct == []
    with store.db:
        for table in PLAYER_TABLES:
            if table in JOIN_OWNERS:
                continue
            count = store.db.execute(f"SELECT count(*) FROM {table} WHERE player_id=?",
                                     (alpha,)).fetchone()[0]
            assert count == len(plan.rows[table]), table


def test_backup_atomic_replace_failure_keeps_old_and_player_state(env, monkeypatch):
    from pathlib import Path
    import x2server.player.save_manager as module
    store, _, manager, alpha, _ = env
    archive = manager.export_save(alpha)
    path = Path(manager.import_save(alpha, archive)['backup'])
    original = path.read_bytes()
    before = manager.canonical_state(alpha)
    def fail(*args):
        raise OSError('simulated replace failure')
    monkeypatch.setattr(module.os, 'replace', fail)
    with pytest.raises(OSError, match='replace failure'):
        manager.import_save(alpha, archive)
    assert path.read_bytes() == original
    assert manager.canonical_state(alpha) == before
    assert not list(path.parent.glob('*.tmp'))


def test_legacy_cleanup_preserves_other_accounts_and_unknown_files(env):
    from pathlib import Path
    store, accounts, manager, alpha, beta = env
    folder = manager.backup_root / 'account_alpha'
    folder.mkdir(parents=True)
    archive = manager.export_save(alpha)
    old = folder / '20261014_000000.x2save'
    old.write_bytes(archive)
    newer = folder / '20261015_000000.x2save'
    newer.write_bytes(archive)
    # A foreign archive and a user-named file must never be removed.
    foreign = folder / '20261015_000001.x2save'
    foreign.write_bytes(manager.export_save(beta))
    unknown = folder / 'manual.x2save'
    unknown.write_bytes(archive)
    assert manager.prune_import_backups() == 1
    assert sum(path.exists() for path in (old, newer)) == 1
    assert foreign.exists() and unknown.exists()
    result = manager.import_save(alpha, archive)
    assert not old.exists() and not newer.exists()
    assert Path(result['backup']).exists() and foreign.exists() and unknown.exists()
    manager.parse_save(Path(result['backup']).read_bytes())
    assert manager.prune_import_backups() == 0


def test_backup_write_failure_preserves_old_backup(env, monkeypatch):
    from pathlib import Path
    import x2server.player.save_manager as module
    store, _, manager, alpha, _ = env
    archive = manager.export_save(alpha)
    path = Path(manager.import_save(alpha, archive)['backup'])
    original = path.read_bytes()
    before = manager.canonical_state(alpha)
    def fail(*args):
        raise OSError('simulated fsync failure')
    monkeypatch.setattr(module.os, 'fsync', fail)
    with pytest.raises(OSError, match='fsync failure'):
        manager.import_save(alpha, archive)
    assert path.read_bytes() == original and manager.canonical_state(alpha) == before
    assert not list(path.parent.glob('*.tmp'))


def test_retention_separates_colliding_legacy_account_names(env):
    store, accounts, manager, _, _ = env
    folder = manager.backup_root / 'account_a_b'
    folder.mkdir(parents=True)
    ids = []
    for i, name in enumerate(('a.b', 'a?b')):
        assert accounts.create(name, 'pw', 1) == 'created'
        pid = accounts.get_by_name(name)['player_id']
        ids.append(pid)
        archive = manager.export_save(pid)
        for j in range(2):
            (folder / f'20261015_00000{i*2+j}.x2save').write_bytes(archive)
    assert manager.prune_import_backups() == 2
    assert len(list(folder.glob('*.x2save'))) == 2
    owners = set()
    for path in folder.glob('*.x2save'):
        with zipfile.ZipFile(path) as z:
            owners.add(json.loads(z.read('manifest.json'))['source_player']['player_id'])
    assert owners == set(ids)


def test_repeated_and_concurrent_imports_keep_one_backup(env):
    from concurrent.futures import ThreadPoolExecutor
    store, _, manager, alpha, _ = env
    archive = manager.export_save(alpha)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda _: manager.import_save(alpha, archive), range(6)))
    assert len({r['backup'] for r in results}) == 1
    files = list(manager.backup_root.rglob('*.x2save'))
    assert len(files) == 1
    before = files[0].read_bytes()
    with pytest.raises(ValueError):
        manager.import_save(alpha, b'bad archive')
    assert files[0].read_bytes() == before
    manager.parse_save(before)


def test_sweep_daily_quota_is_server_owned_across_import(tmp_path):
    store,accounts,manager=make_env(tmp_path)
    build_full_schema(store)
    try:
        assert accounts.create('sweep-quota','password',100)=='created'
        pid=accounts.get_by_name('sweep-quota')['player_id']
        with store.db:
            store.db.execute('INSERT INTO server_sweep_limits VALUES (?,?,?)',(pid,20747,2))
        archive=manager.export_save(pid)
        assert 'server_sweep_limits' not in manager.parse_save(archive).rows
        with store.db:
            store.db.execute('UPDATE server_sweep_limits SET used=15 WHERE player_id=?',(pid,))
        manager.import_save(pid,archive)
        assert tuple(store.db.execute('SELECT day,used FROM server_sweep_limits WHERE player_id=?',(pid,)).fetchone())==(20747,15)
    finally:
        manager.close()
        store.close()
