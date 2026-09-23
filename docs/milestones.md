# Milestones

| Milestone | Goal | Acceptance criteria | Status |
|---|---|---|---|
| M0 Workspace | Reproducible local engineering workspace | Git, src layout, docs, ADRs, config, tests and CI-friendly command | Done |
| M1 Protocol Core | Offline byte-level protocol round trip | PackInt, CRC32, protobuf, framing, stream decoder, registry, inspector and passing tests | Done |
| M2 TCP Connection | Accept and manage client TCP connections | asyncio listener, lifecycle, limits, heartbeat boundary and integration tests | Done |
| M3 WebGameConfig Bootstrap | Supply startup configuration | local HTTP bootstrap fixture and documented routing | Partial |
| Startup / Phase 12 | Stable Revival client lab startup | Three independent cold boots with host GPU + GLESDynamicVersion; normal loading image, Awake, live process and controlInfo HTTP 200 | Done for internal Activity / existing lab data; launcher icon and login not covered |
| FC First Contact | Reach the compatibility TCP server from the original X2 2.4 client | Revival v0.2 reaches local TCP and a real frame decodes | Done: two C2L_Login frames, Phase 13 |
| M4 Login Decode | Decode client login request | real request decoded without business response | Done: CRC/protobuf and local identity verified; redacted evidence committed |
| M5 Minimal Login Response | Produce minimum accepted snapshot | evidence-labelled minimal response and base snapshot accepted by controlled client | Done for minimal base state: Phase 14; not a full inventory/hero snapshot |
| M6 Lobby | Enter and maintain lobby state | required snapshot/push messages identified and served | Partial: Phase 15 reaches visible lobby and empty bag; 26 query/click pairs served, full hero/mobility state pending |
| M7 Guide | Persist early guide progression | groups and steps resume deterministically | Not Started |
| M8 Prepare Mission | Accept first mission preparation | chapter 2010000 / section 2110001 request flow | Not Started |
| M9 Fight Session | Issue coherent fight session values | uuid/sign/data compatibility behavior documented and tested | Not Started |
| M10 First Battle | Complete first local battle path | controlled client reaches battle and exits | Not Started |
| M11 Checkout | Settle first mission and rewards | checkout, RewardData and ItemUpdate remain consistent | Not Started |
| M12 Persistence | Durable player state | schema, migrations, restart and rollback tests | Partial: SQLite v1 base player, restart and conflict rollback verified; gameplay state pending |

Current progress/evidence: [Phase 15](phase15_lobby_account_state.md). Implementation
order after real TCP contact is minimal Login together with player persistence,
then the first playable mission/checkout chain. Persistence should begin with
the first player snapshot rather than waiting until all game services exist.
