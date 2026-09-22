# M3 WebGameConfig/bootstrap

## Why it exists

Phase 5 confirmed that startup performs a WebGameConfig request after loading local config. DNS failure, timeout, exception or non-200 leads to retry/exit. HTTP 200 with an empty body returns without the startup state transition. There is no confirmed automatic local fallback, so a compatible non-empty response is required before First Contact can progress.

Confirmed request behavior:

- HTTP POST;
- approximately 3-second client timeout;
- successful parsing triggers `OnFSMSwitchState(5)`;
- HTTP and game TCP are separate responsibilities.

## Recovery status

The official request path, response field names, envelope, required fields and server-address mapping were **not recovered** in Phase 5. They remain **UNKNOWN**. Therefore M3 is **Partial**.

The committed JSON model is `TEMPORARY_COMPAT`: a strong, non-empty local development format that proves configuration, HTTP lifecycle and endpoint advertisement. It is not claimed to be acceptable to the original client and is not an official capture.

```json
{
  "_fixture": {
    "synthetic": true,
    "schemaStatus": "UNKNOWN_OFFICIAL_BODY_SCHEMA",
    "notOfficialCapture": true
  },
  "gameServer": {"host": "127.0.0.1", "port": 29000},
  "environment": "local-development",
  "clientVersion": "2.4",
  "unknownOfficialFields": []
}
```

The default `/webgameconfig` path is also `TEMPORARY_COMPAT`, not recovered original behavior.

## Components

- `BootstrapConfig` validates and serializes the synthetic model.
- `BootstrapService` owns the fixed route and explicit 200/404/405 behavior.
- `BootstrapHTTPServer` wraps standard-library `ThreadingHTTPServer`; it defaults to localhost, owns its thread and supports async start/stop.
- The HTTP handler never reads arbitrary files, returns tracebacks or embeds authentication data.

The HTTP transport consumes and discards request bodies up to 64 KiB without parsing or logging them. This prevents unread POST bytes from causing a Windows connection reset while bounding input; larger declared bodies receive 413.

The standard library was chosen because this is one fixed development endpoint; a web framework would add dependencies without solving the missing official schema.

## Configuration

| Variable | Default | Status |
|---|---|---|
| `X2_BOOTSTRAP_HOST` | `127.0.0.1` | local safety default |
| `X2_BOOTSTRAP_PORT` | `0` | ephemeral development port |
| `X2_BOOTSTRAP_PATH` | `/webgameconfig` | TEMPORARY_COMPAT |
| `X2_GAME_SERVER_HOST` | TCP host / `127.0.0.1` | local configured value |
| `X2_GAME_SERVER_PORT` | TCP port / `0` | local configured value |
| `X2_ENVIRONMENT` | `local-development` | TEMPORARY_COMPAT |
| `X2_CLIENT_VERSION` | `2.4` | confirmed client version |

Tests start the service on an ephemeral localhost port, POST the fixed endpoint, validate status/content-type/body, parse the result, check configurable game endpoint, verify 404/405 and restart cleanly. No external network is used.

## First Contact use

Before the original client can be started, targeted evidence or controlled routing must identify the real request path and accepted body structure. Replace or adapt the synthetic model only after recording evidence and tests. The bootstrap service must remain separate from TCP Login behavior even if both run in one process.
