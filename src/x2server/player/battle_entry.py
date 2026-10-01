"""Data-driven SectionTable dispatch for every known section type."""
from dataclasses import dataclass
from importlib.resources import files
import json


SECTION_TYPES = {
    0: "Normal", 1: "Endless", 2: "Challenge", 3: "Daily", 4: "PointOfView",
    5: "Training", 6: "WorldBoss", 7: "EndlessWeekly", 8: "ActivityWave",
    9: "ActivityBoss", 10: "ShuangHanStory", 11: "ShuangHanBattle",
    12: "GuildChallenge", 13: "StoryExperience", 14: "ActivityStory",
    15: "ActivityBattle", 16: "ActivityGamePlay1", 17: "ActivityGamePlay2",
    18: "NewBloodMoon", 19: "TowerDefense", 20: "Battlepass",
    21: "MoonChapter", 22: "Monopoly", 23: "Memory",
}


class EntryDenied(ValueError):
    """Client-compatible entry rejection; reason remains server-side."""


@dataclass(frozen=True)
class BattleEntryContext:
    player_id: int
    section_id: int
    section_type: int
    chapter_id: int
    map_id: int
    map_list: tuple[int, ...]
    entry_source: str
    hero_ids: tuple[int, ...]
    stamina_cost: int
    cost_kind: str
    attempt_limit: int | None
    unlock_condition: str
    retry_of_run: str | None = None
    profile_resume: bool = False
    battle_mode: str = "section"
    static_config_source: str = "SectionTable"


class BattleEntryCatalog:
    # Explicit Revival compatibility: the original weekly calendar and attempt
    # accounting have not been proven by live traffic. Static values stay in JSON.
    DAILY_COMPAT = {"enabled": True, "schedule": "always_open", "attempt_limit": None}

    def __init__(self):
        data = json.loads(files("x2server").joinpath("data/battle_entry_catalog.json").read_text(encoding="utf-8"))
        self.sections = {row["SectionID"]: row for row in data["sections"]}
        self.daily_dungeons = {row["ID"]: row for row in data["daily_dungeons"]}
        self.daily_section_to_dungeon = {section: dungeon for dungeon in self.daily_dungeons.values()
                                         for section in dungeon["SectionID"]}
        self.daily_section_ids = {section for dungeon in self.daily_dungeons.values()
                                  for section in dungeon["SectionID"]}

    def resolve(self, *, player_id, request, snapshot, selected_ids, store, economy):
        section_id = request.get("missionId", 0)
        row = self.sections.get(section_id)
        if row is None:
            raise EntryDenied("unknown section")
        section_type = row["Type"]
        if section_type not in SECTION_TYPES:
            raise EntryDenied("unknown SectionType")
        source = "MainMission" if section_type == 0 else SECTION_TYPES[section_type]
        if section_type == 6 and economy:
            try:
                economy.world_boss.battle_admission(player_id,section_id,selected_ids,allow_bound=True)
            except ValueError as exc:
                raise EntryDenied(str(exc)) from exc
        if section_type == 5:
            from .star_chart import catalog, unlocked, state, skill_level
            ability = next(a for a in catalog()['abilities'] if a['ID'] == 39100)
            skill = next(s for s in catalog()['skills'] if s['SkillID'] == 391001)
            level = skill_level(state(snapshot, economy.clock() if economy else 0), 391001)
            if (ability['ID'] not in unlocked(store, player_id)
                    or section_id not in skill['Param2'][:level + 1]):
                raise EntryDenied("star training locked/level unavailable")
        cost = row.get("ManualValue", 0) if economy else 0
        if type(cost) is not int or cost < 0:
            raise EntryDenied("invalid static stamina cost")
        cost_kind = "STATIC_COST" if "ManualValue" in row and economy else "NO_KNOWN_COST"
        open_type = row.get("OpenType", {}).get("value", 0)
        open_param = row.get("OpenParam", 0)
        if open_type == 1 and isinstance(open_param, int) and open_param > 0 and snapshot["level"] < open_param:
            raise EntryDenied("account level requirement")
        if open_type == 2 and open_param and not store.db.execute(
            "SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?", (player_id, open_param)
        ).fetchone():
            raise EntryDenied("prerequisite section not cleared")
        unlock = "E_Level" if open_type == 1 else "E_Stage" if open_type == 2 else "unresolved_gate" if open_type not in (0, 1, 2) else "none"
        attempt_limit = None
        if section_type == 3:
            dungeon = self.daily_section_to_dungeon.get(section_id)
            if not self.DAILY_COMPAT["enabled"]:
                raise EntryDenied("daily entry disabled")
            if dungeon and row["ChapterID"] == dungeon["ID"]:
                position = dungeon["SectionID"].index(section_id)
                if position and not store.db.execute(
                    "SELECT 1 FROM economy_clears WHERE player_id=? AND section_id=?",
                    (player_id, dungeon["SectionID"][position - 1])
                ).fetchone():
                    raise EntryDenied("previous daily section not cleared")
                source = "DailyDungeon"
            attempt_limit = self.DAILY_COMPAT["attempt_limit"]
        maps = tuple(row.get("Maps", ()))
        if not maps:
            raise EntryDenied("section has no map")
        requested_map = request.get("sceneId", 0)
        if requested_map not in maps and (requested_map != 0 or len(maps) != 1):
            raise EntryDenied("map does not belong to section or multi-map choice unresolved")
        if request.get("chapter", 0) != row["ChapterID"]:
            raise EntryDenied("chapter does not match section")
        # Challenge stages use expertMode=true in the real 2.4 client. Their
        # SectionID/ChapterID/Map and static rewards remain authoritative.
        if request.get("checkGm") or request.get("isFromProfile"):
            raise EntryDenied("gm mode/profile resume not implemented")
        return BattleEntryContext(player_id=player_id, section_id=section_id,
            section_type=section_type, chapter_id=row["ChapterID"],
            map_id=requested_map or maps[0], map_list=maps, entry_source=source,
            hero_ids=tuple(selected_ids), stamina_cost=cost, cost_kind=cost_kind,
            attempt_limit=attempt_limit, unlock_condition=unlock)
