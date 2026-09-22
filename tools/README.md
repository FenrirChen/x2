# Tools

Local-only utilities. They must not connect to remote endpoints or log credentials.

- `packet_inspector.py`: prints framing, header, registry and registered body fields for one local binary fixture. Sensitive field names are redacted.
- `generate_synthetic_fixtures.py`: deterministically rebuilds credential-free fixtures used by tests.

```powershell
python tools\generate_synthetic_fixtures.py
python tools\packet_inspector.py tests\fixtures\synthetic_guide_request.bin --direction request
```

