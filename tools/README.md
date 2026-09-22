# Tools

Local-only utilities. They must not connect to remote endpoints or log credentials.

- `packet_inspector.py`: prints framing, header, registry and registered body fields for one local binary fixture. Sensitive field names are redacted.
- `generate_synthetic_fixtures.py`: deterministically rebuilds credential-free fixtures used by tests.
- `first_contact_preflight.py`: performs read-only, fail-closed routing, listener,
  runtime, Git and externally enforced isolation checks before an original-client run.

```powershell
python tools\generate_synthetic_fixtures.py
python tools\packet_inspector.py tests\fixtures\synthetic_guide_request.bin --direction request
```

The First Contact preflight requires explicit target addresses and an
operator-supplied isolation evidence file. It never changes system networking;
without matching deny-by-default evidence it returns `SAFE_TO_RUN=false`.

