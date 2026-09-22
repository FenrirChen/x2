# First Contact runs

No original-client run was performed in Phase 8.

Gate A recovered the two-stage response contract and TCP endpoint mapping, but
the effective packaged `GameConfig.txt` base URL and its HTTP/TLS routing remain
unresolved. Without a proven localhost-only redirect, running the unmodified APK
could contact retired or third-party infrastructure and violates the Phase 8
isolation gate.

```text
Run: NONE
Goal: Gate B preflight
Change: none
Observed: local-only routing cannot yet be guaranteed
Result: First Contact Not Started (below FC0)
Conclusion: do not launch the APK
Next: recover the effective local GameConfig row and prove an isolated redirect
```

No credentials, device identifiers, packets, or runtime logs were collected.
