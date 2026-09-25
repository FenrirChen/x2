---
Document-Type: Historical Report
Date: 2026-09-22
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# First Contact plan — do not execute in Phase 7

## Objective

In the next approved phase, allow a previously unrun original X2 2.4 client to contact the compatibility development services inside a controlled local environment. Do not contact the retired official service or use a real account/token.

## Preconditions

- Work from a clean, tagged/committed repository state.
- Bind bootstrap and TCP only to loopback or an isolated lab interface.
- Establish client routing without changing unrelated APK behavior.
- Enable metadata-only logs; never dump the full Login body.
- Prepare a disposal test identity with no third-party credential if the client permits it; otherwise stop before authentication.

## Success criteria

1. The client's WebGameConfig request reaches the local bootstrap service.
2. Request method, path, headers and body length are recorded without secrets.
3. A response accepted by the client is derived from observed evidence, not guessed fields.
4. The client initiates a connection to the local TCP server.
5. The server receives one complete real frame with valid CRC.
6. Message ID resolves and body decoding succeeds.

Highest goal: identify a real local `C2L_Login` ID 54 request. No Login response or PlayerData should be returned until a separate milestone defines them.

## Evidence sequence

1. Observe only the local bootstrap request metadata; update `docs/bootstrap.md` with CONFIRMED method/path/content expectations.
2. If the synthetic body is rejected, change one evidence-backed field at a time and preserve fixtures/tests.
3. After TCP connect, retain framing metadata first: sizes, ID, request ID and CRC result.
4. Decode locally with redaction. Do not persist a raw authentication body by default.
5. Any change follows Evidence → Specification → Test → Implementation.

## Future fixture policy

Real local client artifacts, if safe to retain, belong under:

```text
tests/fixtures/client/local_client_<message>_request.bin
```

The accompanying README must state:

```text
Captured locally from X2 2.4 client connecting to the compatibility development server.
Not captured from the retired official service.
```

Before committing, inspect for real tokens, third-party credentials, device identifiers and user privacy fields. If sensitive data cannot be reliably removed without invalidating the binary, do **not** save the raw packet. Save only a redacted decoded structure and non-sensitive framing metadata. Never commit a real token or reusable credential.

## Stop conditions

Stop immediately if routing would contact a public/retired endpoint, requires bypassing third-party authentication, exposes real credentials, or demands implementing Login/PlayerData outside the approved milestone.

