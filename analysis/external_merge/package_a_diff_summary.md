# Package A inventory

Source: `D:\demo\x2\other\9.25 loadbyhoshi\9.25 loadbyhoshi`

Files inspected: 114; bytes: 7,917,762.

## Categories

- code_or_schema: 69
- data_or_config: 24
- document: 11
- other: 9
- runtime_artifact: 1

## Comparison with current workspace

- different: 25
- identical: 32
- new_candidate: 32
- no_direct_mapping: 25

Absence from this snapshot is not treated as a deletion request.
Runtime databases, logs, caches, binaries, and external documents are audit-only.

## Directly mapped code and data candidates

- `server/analysis/progression/equipment_progression.json` → `analysis/progression/equipment_progression.json` (identical)
- `server/analysis/progression/equipment_seed_catalog.json` → `analysis/progression/equipment_seed_catalog.json` (identical)
- `server/analysis/progression/equipment_strengthen_catalog.json` → `analysis/progression/equipment_strengthen_catalog.json` (identical)
- `server/src/x2server/__init__.py` → `src/x2server/__init__.py` (identical)
- `server/src/x2server/bootstrap/__init__.py` → `src/x2server/bootstrap/__init__.py` (identical)
- `server/src/x2server/bootstrap/accounts.py` → `src/x2server/bootstrap/accounts.py` (new_candidate)
- `server/src/x2server/bootstrap/http_server.py` → `src/x2server/bootstrap/http_server.py` (identical)
- `server/src/x2server/bootstrap/local_identity.py` → `src/x2server/bootstrap/local_identity.py` (different)
- `server/src/x2server/bootstrap/models.py` → `src/x2server/bootstrap/models.py` (identical)
- `server/src/x2server/bootstrap/service.py` → `src/x2server/bootstrap/service.py` (identical)
- `server/src/x2server/config/__init__.py` → `src/x2server/config/__init__.py` (identical)
- `server/src/x2server/config/logging.py` → `src/x2server/config/logging.py` (identical)
- `server/src/x2server/config/settings.py` → `src/x2server/config/settings.py` (different)
- `server/src/x2server/data/appearance_shop.json` → `src/x2server/data/appearance_shop.json` (new_candidate)
- `server/src/x2server/data/appearance_units.json` → `src/x2server/data/appearance_units.json` (new_candidate)
- `server/src/x2server/data/battle_entry_catalog.json` → `src/x2server/data/battle_entry_catalog.json` (different)
- `server/src/x2server/data/battle_hero_base.json` → `src/x2server/data/battle_hero_base.json` (identical)
- `server/src/x2server/data/battle_shop.json` → `src/x2server/data/battle_shop.json` (new_candidate)
- `server/src/x2server/data/chapter_dp.json` → `src/x2server/data/chapter_dp.json` (new_candidate)
- `server/src/x2server/data/drop_catalog.json` → `src/x2server/data/drop_catalog.json` (new_candidate)
- `server/src/x2server/data/dubbing_catalog.json` → `src/x2server/data/dubbing_catalog.json` (new_candidate)
- `server/src/x2server/data/economy_catalog.json` → `src/x2server/data/economy_catalog.json` (identical)
- `server/src/x2server/data/equib_catalog.json` → `src/x2server/data/equib_catalog.json` (new_candidate)
- `server/src/x2server/data/equib_shop.json` → `src/x2server/data/equib_shop.json` (new_candidate)
- `server/src/x2server/data/gift_contents.json` → `src/x2server/data/gift_contents.json` (new_candidate)
- `server/src/x2server/data/gift_package_shop.json` → `src/x2server/data/gift_package_shop.json` (new_candidate)
- `server/src/x2server/data/godhole_rules.json` → `src/x2server/data/godhole_rules.json` (new_candidate)
- `server/src/x2server/data/icon_catalog.json` → `src/x2server/data/icon_catalog.json` (new_candidate)
- `server/src/x2server/data/jewel_ids.json` → `src/x2server/data/jewel_ids.json` (identical)
- `server/src/x2server/data/modifier_catalog.json` → `src/x2server/data/modifier_catalog.json` (new_candidate)
- `server/src/x2server/data/progression_catalog.json` → `src/x2server/data/progression_catalog.json` (identical)
- `server/src/x2server/data/shop_goods.json` → `src/x2server/data/shop_goods.json` (new_candidate)
- `server/src/x2server/data/wish_catalog.json` → `src/x2server/data/wish_catalog.json` (different)
- `server/src/x2server/gm/__init__.py` → `src/x2server/gm/__init__.py` (new_candidate)
- `server/src/x2server/gm/app.py` → `src/x2server/gm/app.py` (new_candidate)
- `server/src/x2server/gm/http_server.py` → `src/x2server/gm/http_server.py` (new_candidate)
- `server/src/x2server/messages/__init__.py` → `src/x2server/messages/__init__.py` (identical)
- `server/src/x2server/messages/appearance.py` → `src/x2server/messages/appearance.py` (new_candidate)
- `server/src/x2server/messages/battle.py` → `src/x2server/messages/battle.py` (different)
- `server/src/x2server/messages/battle_shop.py` → `src/x2server/messages/battle_shop.py` (new_candidate)
- `server/src/x2server/messages/chat.py` → `src/x2server/messages/chat.py` (identical)
- `server/src/x2server/messages/core.py` → `src/x2server/messages/core.py` (different)
- `server/src/x2server/messages/economy.py` → `src/x2server/messages/economy.py` (different)
- `server/src/x2server/messages/equipment.py` → `src/x2server/messages/equipment.py` (different)
- `server/src/x2server/messages/favor.py` → `src/x2server/messages/favor.py` (new_candidate)
- `server/src/x2server/messages/lobby.py` → `src/x2server/messages/lobby.py` (different)
- `server/src/x2server/messages/progression.py` → `src/x2server/messages/progression.py` (different)
- `server/src/x2server/messages/README.md` → `src/x2server/messages/README.md` (identical)
- `server/src/x2server/messages/wish.py` → `src/x2server/messages/wish.py` (identical)
- `server/src/x2server/network/__init__.py` → `src/x2server/network/__init__.py` (identical)
- `server/src/x2server/network/connection.py` → `src/x2server/network/connection.py` (different)
- `server/src/x2server/network/dispatcher.py` → `src/x2server/network/dispatcher.py` (different)
- `server/src/x2server/network/server.py` → `src/x2server/network/server.py` (different)
- `server/src/x2server/network/session.py` → `src/x2server/network/session.py` (different)
- `server/src/x2server/observability/__init__.py` → `src/x2server/observability/__init__.py` (new_candidate)
- `server/src/x2server/observability/capture.py` → `src/x2server/observability/capture.py` (new_candidate)
- `server/src/x2server/player/__init__.py` → `src/x2server/player/__init__.py` (identical)
- `server/src/x2server/player/appearance.py` → `src/x2server/player/appearance.py` (new_candidate)
- `server/src/x2server/player/battle.py` → `src/x2server/player/battle.py` (different)
- `server/src/x2server/player/battle_entry.py` → `src/x2server/player/battle_entry.py` (different)
- `server/src/x2server/player/battle_shop.py` → `src/x2server/player/battle_shop.py` (new_candidate)
- `server/src/x2server/player/chat.py` → `src/x2server/player/chat.py` (identical)
- `server/src/x2server/player/daily_rewards.py` → `src/x2server/player/daily_rewards.py` (new_candidate)
- `server/src/x2server/player/drop.py` → `src/x2server/player/drop.py` (new_candidate)
- `server/src/x2server/player/economy.py` → `src/x2server/player/economy.py` (different)
- `server/src/x2server/player/equib.py` → `src/x2server/player/equib.py` (new_candidate)
- `server/src/x2server/player/equipment.py` → `src/x2server/player/equipment.py` (different)
- `server/src/x2server/player/favor.py` → `src/x2server/player/favor.py` (new_candidate)
- `server/src/x2server/player/hero.py` → `src/x2server/player/hero.py` (different)
- `server/src/x2server/player/lobby.py` → `src/x2server/player/lobby.py` (different)
- `server/src/x2server/player/login.py` → `src/x2server/player/login.py` (different)
- `server/src/x2server/player/modifier.py` → `src/x2server/player/modifier.py` (new_candidate)
- `server/src/x2server/player/progression.py` → `src/x2server/player/progression.py` (different)
- `server/src/x2server/player/server_clock.py` → `src/x2server/player/server_clock.py` (identical)
- `server/src/x2server/player/skins.py` → `src/x2server/player/skins.py` (new_candidate)
- `server/src/x2server/player/store.py` → `src/x2server/player/store.py` (different)
- `server/src/x2server/player/task_calendar.py` → `src/x2server/player/task_calendar.py` (identical)
- `server/src/x2server/player/wish.py` → `src/x2server/player/wish.py` (different)
- `server/src/x2server/protocol/__init__.py` → `src/x2server/protocol/__init__.py` (identical)
- `server/src/x2server/protocol/codec.py` → `src/x2server/protocol/codec.py` (identical)
- `server/src/x2server/protocol/crc.py` → `src/x2server/protocol/crc.py` (identical)
- `server/src/x2server/protocol/errors.py` → `src/x2server/protocol/errors.py` (identical)
- `server/src/x2server/protocol/framing.py` → `src/x2server/protocol/framing.py` (identical)
- `server/src/x2server/protocol/headers.py` → `src/x2server/protocol/headers.py` (identical)
- `server/src/x2server/protocol/packint.py` → `src/x2server/protocol/packint.py` (identical)
- `server/src/x2server/protocol/protobuf.py` → `src/x2server/protocol/protobuf.py` (identical)
- `server/src/x2server/protocol/recovered_ids.py` → `src/x2server/protocol/recovered_ids.py` (new_candidate)
- `server/src/x2server/protocol/registry.py` → `src/x2server/protocol/registry.py` (different)
- `server/src/x2server/protocol/types.py` → `src/x2server/protocol/types.py` (identical)

## Semantic audit notes

- This is a complete older server snapshot, not a patch. Its 76 shop goods contain 16 contributor-labelled `observed` entries and 60 `pairing` entries. The labels and README are leads, not primary evidence.
- It ships no test files. The documentation mentions tests in another working tree, but those files are absent from this package.
- Its battle, reward, equipment and login modules predate current main's drop budget, ReportCurrency, equipment delivery, task timing and birthday fixes. They cannot replace current files.
- `save/demo.sqlite3`, account configuration and launch scripts are excluded from integration.
