# ADR-0002: Single-service architecture

Status:
Accepted

Context:
The compatibility boundary and minimum client behavior are still being learned. Distributed deployment would add failure modes without evidence of need.

Decision:
Begin with one deployable service and separated internal modules.

Consequences:
Local development and transactions remain straightforward. Modules may be split only after measured operational need.

