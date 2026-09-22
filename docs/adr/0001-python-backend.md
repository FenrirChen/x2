# ADR-0001: Python backend

Status:
Accepted

Context:
The project needs fast iteration on binary protocol fixtures, later HTTP/TCP services and persistence. Current scale requirements are unknown and M1 is offline.

Decision:
Use Python 3.12+, src layout, type hints and pytest. Prefer the standard library in protocol core.

Consequences:
Development and inspection stay simple. Performance-sensitive paths must be measured later instead of assumed.

