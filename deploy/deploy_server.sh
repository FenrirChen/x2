#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL=https://github.com/FenrirChen/x2.git
BRANCH=main
if [[ "$(id -u)" == 0 ]]; then
  ROOT=${X2_DEPLOY_ROOT:-/opt/x2}
  DB_PATH=${X2_DB_PATH:-/var/lib/x2/player.sqlite3}
  ENV_FILE=${X2_ENV_FILE:-/etc/x2server/x2server.env}
  SERVICE_USER=${X2_SERVICE_USER:-x2}
  UNIT_DIR=/etc/systemd/system
  SYSTEMCTL=(systemctl)
  INSTALL_TARGET=multi-user.target
else
  ROOT=${X2_DEPLOY_ROOT:-$HOME/x2-server}
  DB_PATH=${X2_DB_PATH:-$HOME/.local/share/x2/player.sqlite3}
  ENV_FILE=${X2_ENV_FILE:-$HOME/.config/x2server/server.env}
  SERVICE_USER=$(id -un)
  UNIT_DIR=$HOME/.config/systemd/user
  SYSTEMCTL=(systemctl --user)
  INSTALL_TARGET=default.target
fi

for value in "$ROOT" "$DB_PATH" "$ENV_FILE" "$UNIT_DIR" "$SERVICE_USER"; do
  [[ "$value" =~ ^[a-zA-Z0-9_./-]+$ ]] || { echo "Paths/user must not contain spaces or shell metacharacters: $value" >&2; exit 1; }
done
for tool in git python3 systemctl; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
python3 -m venv --help >/dev/null 2>&1 || { echo "Install python3-venv" >&2; exit 1; }

if [[ "$(id -u)" == 0 ]] && ! id "$SERVICE_USER" >/dev/null 2>&1; then
  if command -v useradd >/dev/null; then
    useradd --system --home-dir "$(dirname "$DB_PATH")" --shell /usr/sbin/nologin "$SERVICE_USER"
  else
    echo "Cannot create $SERVICE_USER: install useradd or set X2_SERVICE_USER to an existing non-root user" >&2
    exit 1
  fi
fi
if [[ "$(id -u)" == 0 && "$SERVICE_USER" == root ]]; then
  echo "Refusing to run the game server as root" >&2; exit 1
fi

if [[ ! -e "$ROOT/.git" ]]; then
  [[ ! -e "$ROOT" || -z "$(ls -A "$ROOT")" ]] || { echo "Nonempty non-Git deployment directory: $ROOT" >&2; exit 1; }
  git clone --branch "$BRANCH" "$REPO_URL" "$ROOT"
fi
cd "$ROOT"
[[ -d .git ]] || { echo "Not a Git checkout: $ROOT" >&2; exit 1; }
[[ "$(git remote get-url origin)" == "$REPO_URL" ]] || { echo "Unexpected origin URL" >&2; exit 1; }
[[ "$(git branch --show-current)" == "$BRANCH" ]] || { echo "Checkout must be on $BRANCH" >&2; exit 1; }
[[ -z "$(git status --porcelain)" ]] || { echo "Working tree is dirty; preserve local changes before updating" >&2; exit 1; }
PREVIOUS_COMMIT=$(git rev-parse HEAD)
echo "PREVIOUS_COMMIT=$PREVIOUS_COMMIT"
git fetch origin "$BRANCH"
git merge --ff-only "origin/$BRANCH"

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
mkdir -p runtime logs "$(dirname "$DB_PATH")" "$(dirname "$ENV_FILE")" "$UNIT_DIR"
if [[ "$(id -u)" == 0 ]]; then
  chown -R "$SERVICE_USER:$SERVICE_USER" "$(dirname "$DB_PATH")" runtime logs
fi
if [[ ! -e "$ENV_FILE" ]]; then
  cat > "$ENV_FILE" <<EOF
X2_BIND_HOST=0.0.0.0
X2_PUBLIC_HOST=fenrirchen.com
X2_HTTP_PORT=18080
X2_GAME_PORT=29000
X2_CHAT_PORT=29001
X2_DB_PATH=$DB_PATH
EOF
  chmod 600 "$ENV_FILE"
  if [[ "$(id -u)" == 0 ]]; then chown "$SERVICE_USER:$SERVICE_USER" "$ENV_FILE"; fi
fi

# Preserve every existing database. SQLite online backup handles WAL files safely.
if [[ -f "$DB_PATH" ]]; then
  BACKUP="$DB_PATH.predeploy.$(date -u +%Y%m%dT%H%M%SZ).bak"
  X2_BACKUP_SOURCE="$DB_PATH" X2_BACKUP_TARGET="$BACKUP" .venv/bin/python - <<'PY'
import os, sqlite3
source = sqlite3.connect(f"file:{os.environ['X2_BACKUP_SOURCE']}?mode=ro", uri=True)
target = sqlite3.connect(os.environ['X2_BACKUP_TARGET'])
source.backup(target)
assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
target.close()
source.close()
PY
  echo "DB_BACKUP=$BACKUP"
fi

sed -e "s|@SERVICE_USER@|$SERVICE_USER|g" \
    -e "s|@WORKDIR@|$ROOT|g" -e "s|@ENV_FILE@|$ENV_FILE|g" \
    -e "s|@INSTALL_TARGET@|$INSTALL_TARGET|g" \
    deploy/x2server.service > "$UNIT_DIR/x2server.service"
"${SYSTEMCTL[@]}" daemon-reload
"${SYSTEMCTL[@]}" enable x2server.service
"${SYSTEMCTL[@]}" restart x2server.service

# Read non-secret listener ports from the private EnvironmentFile.
HTTP_PORT=$(sed -n 's/^X2_HTTP_PORT=//p' "$ENV_FILE" | tail -1)
GAME_PORT=$(sed -n 's/^X2_GAME_PORT=//p' "$ENV_FILE" | tail -1)
CHAT_PORT=$(sed -n 's/^X2_CHAT_PORT=//p' "$ENV_FILE" | tail -1)
HTTP_PORT=${HTTP_PORT:-18080}; GAME_PORT=${GAME_PORT:-29000}; CHAT_PORT=${CHAT_PORT:-29001}
HEALTH=0
for _ in $(seq 1 30); do
  if "${SYSTEMCTL[@]}" is-active --quiet x2server.service && \
     X2_CHECK_PORTS="$HTTP_PORT,$GAME_PORT,$CHAT_PORT" python3 - <<'PY'
import os, socket, sys
ports = [int(p) for p in os.environ["X2_CHECK_PORTS"].split(",")]
for port in ports:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            pass
    except OSError:
        sys.exit(1)
PY
  then HEALTH=1; break; fi
  sleep 1
done
if [[ "$HEALTH" != 1 ]]; then
  echo "Service health check failed. PREVIOUS_COMMIT=$PREVIOUS_COMMIT" >&2
  "${SYSTEMCTL[@]}" status x2server.service --no-pager || true
  exit 1
fi
echo "Deployment healthy at commit $(git rev-parse HEAD)"
echo "Open inbound TCP ports: $HTTP_PORT (HTTP login), $GAME_PORT (game), $CHAT_PORT (chat)."
echo "Configure fenrirchen.com A/AAAA to this server. Firewall changes are not automatic."
