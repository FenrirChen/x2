"""Persistent College base snapshots and official building progression."""

from __future__ import annotations

import json
import logging
from importlib.resources import files
from contextlib import contextmanager
import uuid

from x2server.messages.college import COLLEGE_IDS, COLLEGE_SCHEMAS
from x2server.messages.lobby import (BUILDING_BASE_INFO, BUILD_QUEUE, CUSTOMER_INFO, ELEMENT,
                                     EXPLORE_DATA, MISSION_PAIR, PRAY_QUEUE, PRODUCTION_BAR,
                                     TRAINING_DATA, WONDER_QUEUE, zero_queue_row)
from x2server.network.dispatcher import DispatchContext, OutboundMessage
from x2server.protocol.errors import ProtocolError
from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
from x2server.protocol.types import DecodedPacket
from .server_clock import ServerClock

LOGGER = logging.getLogger("x2.college")

E_ERROR_OPT = 13  # GameLogicErrCode.E_ERROR_OPT: refused, unsupported mutation.


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
            "star_energy": 0, "warehouse_gold": 0, "extra_power": 0,
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
        state.setdefault('alchemy', {}).setdefault('element_epoch', row[1])
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
        from .college_alchemy import settle_elements, settle_energy
        # Recover with the OLD level up to each upgrade's completion instant,
        # then use the new speed/capacity. Offline upgrades cannot retroactively
        # grant hours at their new rate.
        queues = (("build_queue", "buildings"), ("wonder_queue", "wonders"))
        for key, field in sorted(queues, key=lambda pair: (state.get(pair[0]) or {}).get('upgradeEndTime', 2**63)):
            queue = state.get(key)
            if queue and queue['upgradeEndTime'] <= self.clock.now():
                settle_elements(state, queue['upgradeEndTime'], self.catalog)
                settle_energy(state, queue['upgradeEndTime'], self.catalog)
                row = next(r for r in state[field] if r['buildingId'] == queue['buildingId'])
                row['buildingLevel'] = queue['target_level']
                completed.append(queue['buildingId'])
                pending = state.setdefault('upgrade_notifications', [])
                if queue['buildingId'] not in pending:
                    pending.append(queue['buildingId'])
                state[key] = None
        settle_elements(state, self.clock.now(), self.catalog)
        settle_energy(state, self.clock.now(), self.catalog)
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

    def alchemy_main(self, player_id: int) -> dict:
        """590/591 snapshot; every list stays a constructed (possibly empty) list."""
        state = self.load(player_id)
        alchemy = state.get("alchemy", {})
        pairs = []
        for pair in alchemy.get("recipe_exp", []):
            if isinstance(pair, dict):
                pairs.append({"Key": int(pair.get("Key", 0)), "Value": int(pair.get("Value", 0))})
            else:
                key, value = pair
                pairs.append({"Key": int(key), "Value": int(value)})
        return {"recipe_exp": pairs,
                "customers": list(alchemy.get("customers", [])),
                "production_bars": list(alchemy.get("production_bars", [])),
                "elements": list(alchemy.get("elements", [])),
                "buff_type": int(alchemy.get("buff_type", 0)),
                "buff_count": int(alchemy.get("buff_count", 0))}


class CollegeService:
    """Network chain for the remaining College flows.

    Building progression and alchemy production use transactional services.
    Other mutations answer E_ERROR_OPT (13) until their rules are implemented.
    """

    # 882 type==3 sends the client down its own refresh chain (0x1B06160).
    ASSIST_UNAVAILABLE = 3
    ALCHEMY_TRANSACTION = 2  # AlchemyType.TRANSACTION, the standard sell order.

    def __init__(self, college: CollegeStateRepository | None = None, clock=None, economy=None):
        self.college = college
        self.clock = clock or (college.clock if college else ServerClock())
        self._catalog: dict | None = None
        from .college_upgrade import BuildingUpgradeService
        self.upgrades = BuildingUpgradeService(college, economy) if college and economy else None
        from .college_alchemy import AlchemyService
        self.alchemy = AlchemyService(college, economy, self._alchemy_main) if college and economy else None
        if self.alchemy:
            self.alchemy.customer = self._customer_for
            self.alchemy.customer_count = self._customer_count
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
        if self.alchemy and flow in self.alchemy.FLOWS:
            return self.alchemy.handle(context, packet, flow, request)
        if self.jobs and flow in self.jobs.FLOWS:
            return self.jobs.handle(context, packet, flow, request)
        if self.prayers and flow in self.prayers.FLOWS:
            return self.prayers.handle(context, packet, flow, request)
        if flow == "SingleCustomerInfo":
            return self._single_customer(context.session.player_id, request)
        if flow == "AlchemyMainData":
            return self._alchemy_main(context.session.player_id)
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

    def _single_customer(self, player_id: int, request: dict) -> OutboundMessage:
        pos_index = int(request.get("posIndex", 0))
        count = self._customer_count(player_id)
        if not 0 <= pos_index < count:
            return OutboundMessage("L2C_SingleCustomerInfo", {"code": E_ERROR_OPT})
        # 593 with code=10 requires a non-null customere (0x189DE24 null-deref),
        # so empty slots are answered with a deterministic customer derived from
        # the official tables, including the persisted refusal rotation.
        customer = self._customer_for(player_id, pos_index)
        return OutboundMessage("L2C_SingleCustomerInfo", {
            "code": 10, "posIndex": pos_index,
            "customere": CUSTOMER_INFO.encode(customer),
            "transactionNum": 1, "transactionLastRecoverTime": 0})

    def _alchemy_main(self, player_id: int) -> OutboundMessage:
        # 591: the handler null-checks every list (first NRE at recipeIdExp,
        # 0x189CE1C) and its reset code expects the six elements / five display
        # positions, so the compatible initial state ships exactly those rows.
        catalog = self._load_catalog()
        state = self.college.load(player_id) if self.college else initial_state()
        if self.college:
            # Settle completion before looking up the active star effects.
            self.college.growth_base(player_id)
            state = self.college.load(player_id)
            # StarEffectValue2 references an older recipe ID domain (292xx).
            # The live 360xx recipe table uses RecipeLevel, as confirmed by
            # GetFurnaceRecipeLevel. Never send nonexistent IDs to TableMgr.
            tier = self.college.catalog.effect(state, 707, 10, star=True)[0]
            recipes = sorted(int(recipe['recipeId']) for rows in catalog['recipes'].values()
                             for level, recipe in rows.items() if int(level) <= tier)
        else:
            recipes = sorted(int(rows["1"]["recipeId"]) for rows in catalog["recipes"].values())
        exp = dict((int(pair["Key"]), int(pair["Value"]))
                   for pair in state.get('alchemy', {}).get('recipe_exp', []))
        elements = sorted(int(element) for element in catalog["recipes"].keys())
        values = {
            "code": 10,
            "recipeIdExp": [MISSION_PAIR.encode({"Key": recipe, "Value": exp.get(recipe, 0)})
                            for recipe in recipes],
            "customeres": [CUSTOMER_INFO.encode(self._customer_for(player_id, pos))
                           for pos in range(self._customer_count(player_id))],
            "productionBars": [PRODUCTION_BAR.encode({})],
            "elements": [ELEMENT.encode(row) for row in state['alchemy'].get('elements', [])]
                        or [ELEMENT.encode({'elementId': element, 'num': 0,
                            'lastRecoverTime': self.clock.now(), 'buyTimesDay': 0}) for element in elements],
            "buffType": 0, "buffCount": 0}
        if self.alchemy:
            with self.college.transaction():
                values.update(self.alchemy.snapshot_fields(state))
                self.college.save(player_id, state)
        elif self.college:
            count = self.college.catalog.effect(state, 701, 7, star=True)[0]
            values['productionBars'] = [PRODUCTION_BAR.encode({'buffId': [0]}) for _ in range(count)]
        return OutboundMessage("L2C_AlchemyMainData", values)

    def _customer_count(self, player_id):
        return 5  # MAX_CUSTOMER_NUM and GlobalParamString.AlchemyCustomerNum

    def _customer_for(self, player_id: int, pos_index: int) -> dict:
        catalog = self._load_catalog()
        customers = catalog["customers"]
        state = self.college.load(player_id) if self.college else initial_state()
        rotations = state.get('alchemy', {}).get('customer_rotations', {})
        # The game day belongs in the seed. Without it the index only moved when
        # the player refused an order, so each position kept showing the same
        # face and demanding the same item forever.
        from .task_calendar import task_period
        day, _ = task_period(1, self.clock.now())
        day_index = day // 86400
        # One god stands at one position: walk the positions in order and skip
        # whatever the lower ones already took, so the five slots never show the
        # same character twice.
        used = set()
        index = 0
        for pos in range(pos_index + 1):
            base = (player_id * 31 + pos * 17 + 5
                    + int(rotations.get(str(pos), 0)) + day_index) % len(customers)
            index = base
            for offset in range(len(customers)):
                candidate = (base + offset) % len(customers)
                if int(customers[candidate]["heroId"]) not in used:
                    index = candidate
                    break
            used.add(int(customers[index]["heroId"]))
        row = customers[index]
        rotation = int(rotations.get(str(pos_index), 0))
        element = str(row["like"])
        first = catalog["recipes"][element]["1"]
        second = catalog["recipes"][element]["2"]
        customer = {"questId": row["sellQuestId"], "itemId": [first["productId"]],
                "itemNum": [first["productNum"]], "type": self.ALCHEMY_TRANSACTION,
                "adviseItemId": second["productId"], "param": int(row["heroId"]), "result": 0}
        saved = state.get('alchemy', {}).get('customer_orders', {}).get(str(pos_index), {})
        if saved.get('rotation') == rotation and saved.get('questId') == customer['questId']:
            for key in ('itemId', 'itemNum', 'adviseItemId'):
                customer[key] = saved[key]
        return customer

    def _load_catalog(self) -> dict:
        if self._catalog is None:
            self._catalog = json.loads(files("x2server").joinpath(
                "data/college_alchemy_catalog.json").read_text(encoding="utf-8"))
        return self._catalog
