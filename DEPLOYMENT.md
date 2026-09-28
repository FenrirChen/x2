# X2 Revival Linux deployment

This deploys the current compatibility server. It does not deploy an APK or
change DNS. The source repository must already be available at
`https://github.com/FenrirChen/x2.git` on its `main` branch.

## Server prerequisites

- Linux with systemd, Git, Python **3.12+**, `python3-venv`, and outbound GitHub access.
- DNS: `fenrirchen.com` A record must point to the server's public IPv4.
- Open inbound TCP **18080** (HTTP login/bootstrap), **29000** (game protocol),
  and **29001** (chat). The script prints these ports; it never edits the firewall.
- The login endpoint is currently plain HTTP because that is the confirmed
  Revival client protocol. Passwords traverse the network without TLS. Put
  HTTPS termination and a matching client configuration in place before
  accepting sensitive credentials from the public.

## First deployment and updates

Copy `deploy/deploy_server.sh` to the Linux host, then run:

```bash
chmod +x deploy_server.sh
sudo ./deploy_server.sh
```

The same command updates the checkout with a fast-forward only pull, refreshes
the virtual environment, backs up an existing SQLite database, and restarts the
systemd service. It refuses a dirty checkout or an unexpected Git origin.
The first run creates a non-root `x2` service user and uses `/opt/x2` for code,
`/var/lib/x2/player.sqlite3` for player data, and
`/etc/x2server/x2server.env` for local configuration. It never replaces or
deletes the database. Schema v2 migration is non-destructive and occurs when
the server starts. The script prints `PREVIOUS_COMMIT` and the database backup
path for recovery if an update fails.

Without root, the same script uses a systemd **user** unit under
`~/.config/systemd/user`, code under `~/x2-server`, and data under
`~/.local/share/x2`. That user must have a working systemd user session;
enable lingering separately if it must run while logged out.

Edit only the server's private EnvironmentFile to customize addresses or
ports. [`.env.example`](.env.example) lists the supported variables.
`X2_PUBLIC_HOST` is what the server returns to clients; `X2_BIND_HOST=0.0.0.0`
listens on network interfaces. Keep `X2_LOCAL_ACCOUNT` and
`X2_LOCAL_PASSWORD` unset for public self-registration. Never commit private
EnvironmentFiles or put account passwords into shell commands.

## Service status and logs

```bash
systemctl status x2server
journalctl -u x2server -f
```

For a user service, add `--user` to `systemctl` and `journalctl`. The script
checks that systemd reports active and all three ports accept local TCP
connections. It leaves the old database intact on failure and prints the
previous commit for a controlled code rollback.

## Persistent data and backup

The production database is outside the Git checkout. The update script creates
a timestamped SQLite online backup alongside it before restarting. An
additional manual backup can be made without stopping the server:

```bash
sudo -u x2 /opt/x2/.venv/bin/python - <<'PY'
import sqlite3
source = sqlite3.connect('file:/var/lib/x2/player.sqlite3?mode=ro', uri=True)
target = sqlite3.connect('/var/lib/x2/player.manual-backup.sqlite3')
source.backup(target)
target.close()
source.close()
PY
```

## APK endpoint matrix

| Purpose | Old local endpoint | Public endpoint | Source |
|---|---|---|---|
| Login/bootstrap HTTP | `http://10.0.2.2:18080` | `http://fenrirchen.com:18080` | GameConfig row 0 `Login_Url` |
| Game TCP | `10.0.2.2:29000` | `fenrirchen.com:29000` | Server `/apply/httpLogin` response |
| Chat TCP | `10.0.2.2:29001` | `fenrirchen.com:29001` | Server `/apply/chatNode` response |

The APK patch is reproducible with `tools/patch_public_endpoint.py`; its
input hash is locked to the confirmed Revival v0.2 build. The resulting binary
is deliberately excluded from Git. Existing local signing material produces
a test-signed APK, but its certificate differs from the installed v0.2 APK;
Android cannot update that installation in place. Preserve the installed
app data before uninstalling, or provide the matching release signing key.

The 2026-09-28 test-signed APK installed and launched in a disposable read-only
Android AVD. A successful connection to `fenrirchen.com` could not yet be
verified: the domain's A record exists, but ports 18080/29000/29001 are not
reachable from the development machine, and the AVD's external HTTP proxy
also failed its connectivity checks. Deploy the server and open the three
ports before final end-to-end APK acceptance.
