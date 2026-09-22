# ADR-0004: Asyncio network boundary

Status:
Accepted

Context:
M1 already provides deterministic stream framing. M2 needs many independent long-lived TCP connections, backpressure, timeouts and graceful shutdown without adding a framework.

Decision:
Use standard-library asyncio streams. The server owns connection tasks; each connection owns one decoder and session metadata. Dispatchers return optional response values, which the connection serializes through the M1 codec.

Consequences:
The byte path remains small and testable on localhost. Business behavior cannot access raw socket lifecycle unless a later, evidence-backed requirement adds an explicit interface.

