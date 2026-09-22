# ADR-0003: Protocol-layer separation

Status:
Accepted

Context:
Recovered byte rules are evidence-driven and must not be coupled to provisional login, guide or player behavior.

Decision:
Keep protocol codecs, network lifecycle and business state in separate packages. Protocol code accepts bytes and typed values, not databases or handlers.

Consequences:
Fixtures can prove byte compatibility offline. Business behavior can evolve without rewriting framing.

