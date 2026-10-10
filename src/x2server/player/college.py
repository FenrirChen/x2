"""Persistent College base snapshots and official building progression."""

from __future__ import annotations

import json
import logging
from importlib.resources import files
from contextlib import contextmanager
import uuid

from x2server.messages.college import COLLEGE_IDS, COLLEGE_SCHEMAS
from x2server.messages.lobby import (BUILDING_BASE_INFO, BUILD_QUEUE,
                                     EXPLORE_DATA, PRAY_QUEUE,
                                     TRAINING_DATA, WONDER_QUEUE, zero_queue_row)
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from x2server.protocol.types import DecodedPacket
from .server_clock import ServerClock

LOGGER = logging.getLogger("x2.college")

E_ERROR_OPT = 13  # GameLogicErrCode.E_ERROR_OPT: refused, unsupported mutation.

# 星能: 每小时恢复 2 点, 上限 96。与离线端星能口径一致 (alchemy.py 的元素/星能
# 结算同源); 存档里 ``star_energy`` 的 -1 表示"未初始化", 首次结算直接给满。
STAR_ENERGY_PER_HOUR = 2
STAR_ENERGY_CAP = 96


def settle_star_energy(state: dict, now: int) -> None:
    """Lazily recover 星能; 逐字对齐离线端 college.cpp 的 college_settle 星能部分。

    ``-1`` 是"未初始化", 首次结算直接给满。恢复只推进已结算的整数刻, 余数留到下次;
    满值/未初始化时把结算时刻设为 now。``star_energy_at`` 存上一次结算的 unix;
    ``star_gain_time`` 是给 584 用的"下次恢复时刻" (满值时等于 now)。
    """
    energy = int(state.get("star_energy", -1))
    at = int(state.get("star_energy_at", 0))
    if energy < 0:
        energy, at = STAR_ENERGY_CAP, now
    elif energy >= STAR_ENERGY_CAP:
        at = now
    else:
        if at <= 0 or at > now:
            at = now
        elapsed = now - at
        if elapsed > 0:
            ticks = elapsed * STAR_ENERGY_PER_HOUR // 3600
            if ticks > 0:
                energy = min(STAR_ENERGY_CAP, energy + ticks)
                at = (now if energy >= STAR_ENERGY_CAP
                      else at + ticks * 3600 // STAR_ENERGY_PER_HOUR)
    state["star_energy"] = energy
    state["star_energy_at"] = at
    state["star_gain_time"] = at if energy >= STAR_ENERGY_CAP else at + 3600 // STAR_ENERGY_PER_HOUR


def initial_state() -> dict:
    """Copy only initial levels/stars explicitly present in CollegeBuilding."""
    rows = json.loads(files("x2server").joinpath("data/college_initial_buildings.json").read_text(encoding="utf-8"))
    buildings, wonders = [], []
    for row in rows:
        info = {"buildingId": row["id"], "buildingLevel": row["level"]}
        if "star" in row:
            info["buildingStar"] = row["star"]
        (buildings if row["type"] == "building" else wonders).append(info)
    return {"version": 1, "buildings": buildings, "wonders": wonders,
            "star_energy": -1, "warehouse_gold": 0, "extra_power": 0,
            "gold_gain_time": 0, "star_gain_time": 0, "washing_count_day": 0,
            "explore": [], "training": [], "pray": [], "ruins": [],
            "alchemy": {"recipe_exp": [], "customers": [], "production_bars": [],
                        "elements": [], "buff_type": 0, "buff_count": 0}}


class CollegeStateRepository:
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or ServerClock()
        from .college_upgrade import UpgradeCatalog
        self.catalog = UpgradeCatalog()
        with store.db:
            store.db.execute("""CREATE TABLE IF NOT EXISTS college_state (
                player_id INTEGER PRIMARY KEY REFERENCES players(id),
                version INTEGER NOT NULL, state_json TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)""")

    @contextmanager
    def transaction(self):
        """Nested snapshots must not commit a caller's inventory transaction."""
        name = 'college_' + uuid.uuid4().hex
        self.store.db.execute('SAVEPOINT ' + name)
        try:
            yield
        except BaseException:
            self.store.db.execute('ROLLBACK TO ' + name)
            self.store.db.execute('RELEASE ' + name)
            raise
        else:
            self.store.db.execute('RELEASE ' + name)

    def load(self, player_id: int) -> dict:
        now = self.clock.now()
        with self.transaction():
            self.store.db.execute("""INSERT OR IGNORE INTO college_state
                (player_id,version,state_json,created_at,updated_at) VALUES (?,?,?,?,?)""",
                (player_id, 1, json.dumps(initial_state(), sort_keys=True), now, now))
        row = self.store.db.execute("SELECT state_json,created_at FROM college_state WHERE player_id=?", (player_id,)).fetchone()
        state = json.loads(row[0])
        # Older saves predate the eighth civilization row. Add missing official
        # rows only, preserving every saved level/star, queue and resource.
        changed = False
        for key in ('buildings', 'wonders'):
            present = {r['buildingId'] for r in state[key]}
            for initial in initial_state()[key]:
                if initial['buildingId'] not in present:
                    state[key].append(initial)
                    changed = True
        if changed:
            self.save(player_id, state)
        if int(state.get('star_gain_time', 0)) <= 0:
            state['star_gain_time'] = row[1]
        return state

    @classmethod
    def settled_existing(cls, store, player_id, clock=None):
        """Settle an existing save without schema setup/committing its caller."""
        repo = object.__new__(cls)
        repo.store, repo.clock = store, clock or ServerClock()
        from .college_upgrade import UpgradeCatalog
        repo.catalog = UpgradeCatalog()
        with repo.transaction():
            state = repo.load(player_id)
            before = json.dumps(state, sort_keys=True)
            repo.settle(state)
            if json.dumps(state, sort_keys=True) != before:
                repo.save(player_id, state)
        return state

    def save(self, player_id: int, state: dict) -> None:
        if state.get("version") != 1:
            raise ValueError("unsupported college state version")
        with self.transaction():
            cursor = self.store.db.execute("""UPDATE college_state SET state_json=?,updated_at=?
                WHERE player_id=? AND version=1""",
                (json.dumps(state, sort_keys=True), self.clock.now(), player_id))
            if cursor.rowcount != 1:
                raise ValueError("college state missing or version mismatch")

    # ``peek``/``stage`` are the bare read/write pair AlchemyService uses so it can
    # read-modify-write 星能 inside the economy's transaction without committing its
    # savepoint.  Both still nest through this repository's own SAVEPOINT wrapper.
    def peek(self, player_id: int) -> dict:
        return self.load(player_id)

    def stage(self, player_id: int, state: dict) -> None:
        self.save(player_id, state)

    def growth_base(self, player_id: int) -> dict:
        with self.transaction():
            state = self.load(player_id)
            before = json.dumps(state, sort_keys=True)
            self.settle(state)
            if json.dumps(state, sort_keys=True) != before:
                self.save(player_id, state)
        # The client deserializer (SilentOrbit) leaves absent repeated/singular
        # fields NULL and several consumers deref them unconditionally
        # (RefreshTrainRedDot, upgrade widget), so every list carries one
        # zero-filled idle entry and the queues are always present objects.
        result = {"buildingList": [BUILDING_BASE_INFO.encode(row) for row in state["buildings"]],
                  "civilization": [BUILDING_BASE_INFO.encode(row) for row in state["wonders"]],
                  "starEnergy": state["star_energy"], "warehouseGold": state["warehouse_gold"],
                  "extraPower": state["extra_power"], "goldGainTime": state["gold_gain_time"],
                  "starGainTime": state["star_gain_time"], "washingCountDay": state["washing_count_day"],
                  "exploreList": self.jobs_wire(state, 'explore'),
                  "trainingList": self.jobs_wire(state, 'training'),
                  "prayQueue": self.prayers_wire(state),
                  "buildQueue": self.queue_wire(state, "build_queue", BUILD_QUEUE),
                  "wonderQueue": self.queue_wire(state, "wonder_queue", WONDER_QUEUE)}
        return result

    @staticmethod
    def prayers_wire(state):
        # Civilization.Refresh (0x1db5e64..0x1db5f38) replaces its cached
        # PrayQueue ONLY when buildingId matches. Omitting a claimed building
        # leaves the old status=2 object and its claim prompt alive.
        rows = {r['buildingId']: r for r in state.get('pray', [])}
        active = list(rows.values())
        idle = [{'buildingId': r['buildingId']} for r in state['wonders']
                if r['buildingId'] not in rows]
        return [PRAY_QUEUE.encode({f.name: row.get(f.name, 0) for f in PRAY_QUEUE.fields})
                for row in active + idle]

    def jobs_wire(self, state, kind):
        training = kind == 'training'
        schema = TRAINING_DATA if training else EXPLORE_DATA
        id_field = 'trainingId' if training else 'exploreId'
        capacity = self.catalog.effect(state, 704 if training else 705,
                                       6 if training else 1, star=True)[0]
        rows = {r[id_field]: r for r in state.get(kind, []) if isinstance(r, dict)}
        fields = {f.name for f in schema.fields}
        result = []
        for index in range(max(1, capacity)):
            row = dict(rows.get(index, {id_field: index}))
            # Native UI enums differ: training 0=locked/1=idle/2=running/3=done;
            # exploration 0=locked/1=idle/2=occupied (end time decides claim).
            row.setdefault('trainingStatus' if training else 'exploreStatus',
                           1 if index < capacity else 0)
            if training:
                # RefreshOpen looks up CollegeLevel by this field, not Building.
                if row.get('buildID') not in self.catalog.levels:
                    building = self.catalog.state_row(state, 704)
                    row['buildID'] = self.catalog.row(704, building['buildingLevel'])['BuildID']
            else:
                row['heroList'] = row.get('heroList') or [0]
            result.append(schema.encode({k: v for k, v in row.items() if k in fields}))
        return result

    @staticmethod
    def queue_wire(state, key, schema):
        queue = state.get(key) or {}
        return schema.encode({k: v for k, v in queue.items() if k != 'target_level'})

    def settle(self, state):
        """Apply each persisted target once; offline progress uses the same clock."""
        completed = []
        # 星能随时间恢复; 装备洗炼/元素恢复改由 AlchemyStateRepository (player/alchemy.py)
        # 自己的表按需结算, 学院快照不再参与炼金元素。
        queues = (("build_queue", "buildings"), ("wonder_queue", "wonders"))
        for key, field in sorted(queues, key=lambda pair: (state.get(pair[0]) or {}).get('upgradeEndTime', 2**63)):
            queue = state.get(key)
            if queue and queue['upgradeEndTime'] <= self.clock.now():
                settle_star_energy(state, queue['upgradeEndTime'])
                row = next(r for r in state[field] if r['buildingId'] == queue['buildingId'])
                row['buildingLevel'] = queue['target_level']
                completed.append(queue['buildingId'])
                pending = state.setdefault('upgrade_notifications', [])
                if queue['buildingId'] not in pending:
                    pending.append(queue['buildingId'])
                state[key] = None
        settle_star_energy(state, self.clock.now())
        for row in state.get('pray', []):
            row['prayStatus'] = 2 if row['prayEndTime'] <= self.clock.now() else 1
        for kind, prefix in (('training', 'training'), ('explore', 'explore')):
            for row in state.get(kind, []):
                if isinstance(row, dict):
                    # Derive from persisted jobs, also correcting old status values
                    # without discarding a hero, timer or unclaimed reward.
                    row[prefix + 'Status'] = ((3 if row['trainingEndTime'] <= self.clock.now() else 2)
                                             if kind == 'training' else 2)
        return completed

    def unlock_ruins(self, player_id: int) -> list:
        """622/623 is a state query: repeat calls must return the same stored ruins."""
        with self.transaction():
            state = self.load(player_id)
            if not state.get('ruins'):
                state['ruins'] = [{'ruinId': 34001, 'exp': 0, 'queueCount': 0}]
                self.save(player_id, state)
            return [dict(row) for row in state['ruins']]


class CollegeService:
    """Network chain for the remaining College flows.

    Building progression and the other transactional services are wired here; the
    alchemy 炼金 flows are owned by AlchemyService (player/alchemy.py).
    Other mutations answer E_ERROR_OPT (13) until their rules are implemented.
    """

    # 882 type==3 sends the client down its own refresh chain (0x1B06160).
    ASSIST_UNAVAILABLE = 3

    def __init__(self, college: CollegeStateRepository | None = None, clock=None, economy=None):
        self.college = college
        self.clock = clock or (college.clock if college else ServerClock())
        from .college_upgrade import BuildingUpgradeService
        self.upgrades = BuildingUpgradeService(college, economy) if college and economy else None
        from .college_jobs import CollegeJobsService
        self.jobs = CollegeJobsService(college, economy) if college and economy else None
        from .college_pray import CollegePrayService
        self.prayers = CollegePrayService(college, economy, self.upgrades) if college and economy else None

    def handlers(self):
        return {"C2L_" + name: self.dispatch for name, _, _ in COLLEGE_IDS}

    async def dispatch(self, context: DispatchContext, packet: DecodedPacket) -> OutboundMessage:
        if context.session.player_id is None:
            raise ProtocolError("college request before login")
        name = CORE_MESSAGE_REGISTRY.name_for(packet.message_id)
        flow = name[len("C2L_"):]
        request = COLLEGE_SCHEMAS[name].decode(packet.body)
        if self.upgrades and flow in ("BuildingUpgrade", "BuildStarUP", "BuildSpeedUP", "BuildCrystalFinish"):
            return self.upgrades.handle(context, packet, flow, request)
        if self.jobs and flow in self.jobs.FLOWS:
            return self.jobs.handle(context, packet, flow, request)
        if self.prayers and flow in self.prayers.FLOWS:
            return self.prayers.handle(context, packet, flow, request)
        if flow == "QueryFirstReCharge":
            # Read-only queries: this local account has no recharge activities.
            return OutboundMessage("L2C_QueryFirstReCharge", {"code": 10, "state": 0})
        if flow == "QueryAccumulateReCharge":
            return OutboundMessage("L2C_QueryAccumulateReCharge",
                {"code": 10, "accumulateReChargeDataList": [], "totalMoney": 0,
                 "totalRechargeExp": 0})
        if flow == "HelpPowerSpeedValid":
            # This is also the LOCAL acceleration-window gate. Reply type 1/2
            # invokes the callback which opens it (OnGetHelpPowerSpeedVaild).
            kind = request.get('type', 0)
            if kind in (1, 2) and self.college:
                self.college.growth_base(context.session.player_id)
                state = self.college.load(context.session.player_id)
                queue = state.get('build_queue' if kind == 1 else 'wonder_queue')
                return OutboundMessage('L2C_HelpPowerSpeedValid',
                    {'code': 10 if queue else E_ERROR_OPT, 'type': kind})
            return OutboundMessage("L2C_HelpPowerSpeedValid",
                {"code": 10, "type": self.ASSIST_UNAVAILABLE})
        if flow == "HelpPowerSpeed":
            return OutboundMessage("L2C_HelpPowerSpeed",
                {"code": 10, "helpPowerSpeedParam": [], "helpPower": 0})
        LOGGER.info("college mutation refused player=%s flow=%s request=%s",
                    context.session.player_id, flow, request)
        return OutboundMessage("L2C_" + flow, {"code": E_ERROR_OPT})
