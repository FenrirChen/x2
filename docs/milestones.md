# Milestones

| Milestone | Goal | Acceptance criteria | Status |
|---|---|---|---|
| M0 Workspace | Reproducible local engineering workspace | Git, src layout, docs, ADRs, config, tests and CI-friendly command | Done |
| M1 Protocol Core | Offline byte-level protocol round trip | PackInt, CRC32, protobuf, framing, stream decoder, registry, inspector and passing tests | Done |
| M2 TCP Connection | Accept and manage client TCP connections | asyncio listener, lifecycle, limits, heartbeat boundary and integration tests | Done |
| M3 WebGameConfig Bootstrap | Supply startup configuration | local HTTP bootstrap fixture and documented routing | In Progress |
| M4 Login Decode | Decode client login request | captured/local fixture decoded without business response | Not Started |
| M5 Minimal Login Response | Produce minimum accepted snapshot | evidence-labelled response fixture accepted by controlled client test | Not Started |
| M6 Lobby | Enter and maintain lobby state | required snapshot/push messages identified and served | Not Started |
| M7 Guide | Persist early guide progression | groups and steps resume deterministically | Not Started |
| M8 Prepare Mission | Accept first mission preparation | chapter 2010000 / section 2110001 request flow | Not Started |
| M9 Fight Session | Issue coherent fight session values | uuid/sign/data compatibility behavior documented and tested | Not Started |
| M10 First Battle | Complete first local battle path | controlled client reaches battle and exits | Not Started |
| M11 Checkout | Settle first mission and rewards | checkout, RewardData and ItemUpdate remain consistent | Not Started |
| M12 Persistence | Durable player state | schema, migrations, restart and rollback tests | Not Started |
