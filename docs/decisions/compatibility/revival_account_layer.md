# Revival account layer

Decision (2026-09-28): preserve the client's observed Account mode HTTP form
endpoints and introduce a local, password-hashed account table. Registering a
new identity creates its minimal player row in the same SQLite transaction.
The recovered client does not reveal the original publisher's account backend
or first-login grants, so this is REVIVAL_COMPATIBILITY, not an official rule.

The client's visitor path uses an empty password and one of only 10000 names.
It is rejected until a collision-safe guest identity is available. Unknown
password logins do not register accounts. Public deployment remains blocked
pending actual client validation and public security hardening.
