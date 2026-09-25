# ADR-0005: Separate bootstrap service

Status:
Accepted

Context:
The client performs an HTTP WebGameConfig step before opening its long-lived game TCP connection. The official body schema remains unknown, while HTTP lifecycle and local configuration still need deterministic tests.

Decision:
Keep bootstrap models/service/HTTP transport separate from the game TCP protocol. Use standard-library ThreadingHTTPServer for one fixed localhost development endpoint. Label the JSON shape and default path TEMPORARY_COMPAT until client evidence exists.

Consequences:
HTTP startup configuration can evolve without contaminating packet framing or Login. Running both services in one future process does not merge their responsibilities. M3 remains Partial until the official accepted request/response shape is recovered through controlled First Contact evidence.

