# Development

## Local checks

```powershell
python -m pytest
ruff check .
mypy src tools
```

Only pytest is required for M0/M1 acceptance. If ruff or mypy is unavailable, report that explicitly rather than silently skipping it.

## Configuration and secrets

Non-secret defaults live under `x2server.config`. Deployment-specific values come from environment variables or an untracked local configuration file. Never commit `.env`, tokens, passwords, private keys, real user credentials or production addresses.

## Evidence workflow

1. Record the source and status: CONFIRMED, INFERRED or TEMPORARY_COMPAT.
2. Update `docs/protocol_spec.md`.
3. Add or amend a test that expresses the evidence.
4. Implement the smallest change that satisfies the test.
5. Run offline checks and inspect `git status` before committing.

Do not change a protocol expectation solely to make an implementation pass.

