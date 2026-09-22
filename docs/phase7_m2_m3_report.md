# Phase 7 — M2/M3 implementation report

Date: 2026-09-22

## 1. Git starting state

Phase 7 began on a clean `feat/protocol-core` branch at `c949cc7`. The reported Phase 6 history was present and the original 75 tests passed with zero failures. No conflicting or uncommitted files existed.

The tested branch was merged into `main` with non-fast-forward merge `59c0ded` (`merge: complete protocol core milestone`). Local tag `v0.1-protocol-core` points to that merge. Development then moved to `feat/network-bootstrap`. Nothing was pushed and no remote repository was created.

## 2. M2 status and architecture

M2 is **Done**.

`X2TCPServer` owns listener, accepted connection objects and their tasks. Each `X2Connection` owns one reader/writer, process-local connection ID, peer address, `SessionState`, existing M1 `PacketStreamDecoder`, timestamps and close state.

```text
client bytes
→ asyncio listener
→ X2Connection.read
→ PacketStreamDecoder.feed
→ 0..N DecodedPacket
→ Dispatcher
→ optional OutboundMessage
→ ProtocolCodec + ResponseHeader
→ writer.write + await drain
```

The network layer reuses M1 framing/CRC/protobuf and does not duplicate protocol code. Connection ID, network session ID and future player ID remain distinct. The default listener is `127.0.0.1`; host, port, read/write/idle timeouts, maximum connections, chunk size and packet limit are configurable.

## 3. TCP lifecycle and errors

- Reads are stream-oriented; one read is never treated as one packet.
- EOF with partial buffered data is logged and the connection closes.
- CRC mismatch, malformed PackInt, oversized length, timeout, reset and broken pipe affect only the current connection.
- Writes call `writer.write` and `await writer.drain` under a configured timeout.
- Shutdown closes the accept socket, closes active writers, awaits owned tasks and cancels only tasks that exceed the shutdown bound.
- Tests use queues and server lifecycle conditions rather than wall-clock sleeps.

## 4. Dispatcher behavior

The dispatcher performs only message ID→registry→optional handler resolution.

- Known message with handler: handler may return one registered response value.
- Known but unimplemented message, including `C2L_Login` 54: metadata-only log and no response.
- Unknown ID: protocol warning and no response; listener remains alive.

Logs carry connection ID, peer, message ID/name and request ID. Message bodies, Login token and authentication payloads are not logged. No Login handler or fake `L2C_Login` exists.

## 5. Socket integration coverage

Automated localhost tests cover:

- start/connect/clean close;
- synthetic GuideStep ID 374 and request ID recognition;
- request/response correlation through L2C_GuideStep 375;
- one packet split across three writes;
- two packets in one write;
- complete packet plus partial next packet;
- bad CRC isolation followed by a valid second connection;
- malformed and oversized lengths;
- incomplete packet at EOF;
- graceful shutdown with an active client.

## 6. M3 recovery level

M3 is **Partial**.

Phase 5 confirms that WebGameConfig uses HTTP POST with an approximately 3-second timeout; network failure/non-200 triggers retry or exit, empty 200 stalls, and successful parsing advances the startup state. It does **not** recover the official request path, body field names, required envelope or accepted server-address mapping. Those remain UNKNOWN.

The implementation therefore supplies a reliable fixed-route localhost HTTP layer and a strictly labelled `TEMPORARY_COMPAT` JSON model. It does not claim that the original client accepts the committed JSON.

## 7. Bootstrap fixture and service

`synthetic_webgameconfig.json` contains:

- an explicit synthetic/not-official marker;
- schema status `UNKNOWN_OFFICIAL_BODY_SCHEMA`;
- configurable game server host/port;
- local environment and client version;
- an explicit list reserved for unknown official fields.

`BootstrapService` returns 200 only for POST to its configured path, 405 for the wrong method and 404 for unknown paths. `BootstrapHTTPServer` wraps standard-library `ThreadingHTTPServer`, binds localhost by default and supports async start/stop. It cannot read arbitrary files, does not return tracebacks and contains no token. Integration requests explicitly disable host proxy settings to guarantee offline localhost traffic.

## 8. Verification

```text
pytest: 101 passed, 0 failed
ruff: unavailable
mypy: unavailable
```

The original 75 M1 tests remain green: zero regression. Ruff and mypy remain configured but were not installed, in accordance with the instruction not to download tools merely for formality.

## 9. Phase 7 commits

- `59c0ded merge: complete protocol core milestone` (`main`, tag `v0.1-protocol-core`)
- `c42b2ab feat(network): add asyncio TCP connection layer`
- `be4c4cc feat(bootstrap): add WebGameConfig development service`
- `docs: record Phase 7 M2/M3 results` (this report)

Phase 7 work remains on `feat/network-bootstrap` and is not merged into `main`.

## 10. Remaining unknowns

1. Official WebGameConfig URL/path, request body and response schema.
2. Which response field(s) supply TCP host/port and any required version/environment envelope.
3. Whether the original client accepts plain HTTP in the controlled routing environment.
4. Minimum valid Login request/response semantics; no handler is implemented.
5. Real client packet tolerance and timing beyond synthetic fixture coverage.

## 11. First Contact readiness

**B** — TCP infrastructure is complete and locally tested; bootstrap HTTP lifecycle is complete, but the original client's accepted WebGameConfig structure remains a key unknown. The remaining work before controlled First Contact is targeted routing and evidence capture, not more speculative server business logic.

The next-phase procedure is documented in `docs/first_contact_plan.md`. Phase 7 did not start the APK, connect a retired service, capture credentials, implement Login or add a database.

