# Architecture

The early compatibility backend is a single Python service with strict internal boundaries:

```text
business (future)
    ↓ typed message values
protocol: protobuf schema ↔ packet framing
    ↓ bytes / decoded packet
network: connection and session lifecycle (M2)
    ↓
TCP
```

Configuration is read separately from code. Runtime data and secrets are never committed. Reverse-engineering evidence remains outside the repository and is referenced through `reverse_data/README.md` and `docs/reverse_engineering_sources.md`.

M1 implements only deterministic byte transformations and a thin session state model. It deliberately has no socket listener, authentication, player state or game logic.

Logging uses the standard `logging` package. Future structured context should include connection ID, message ID/name and request ID; token values and complete authentication payloads must never be logged.

