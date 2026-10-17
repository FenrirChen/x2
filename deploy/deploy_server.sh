#!/usr/bin/env bash
set -Eeuo pipefail

REPO_URL=https://github.com/FenrirChen/x2.git
BRANCH=main
STAGE=preflight
phase() { STAGE=$1; printf '\n[%s] %s\n' "$(date '+%F %T %z')" "$STAGE"; }
failed() {
  local result=$1 line=$2
  trap - ERR
  echo "Deployment failed: stage=$STAGE line=$line exit=$result PREVIOUS_COMMIT=${PREVIOUS_COMMIT:-unknown}" >&2
  echo "No automatic code rollback, database restore, or service recovery was attempted. Inspect systemctl status and this error before manual recovery." >&2
  exit "$result"
}
trap 'failed "$?" "$LINENO"' ERR
phase preflight
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
for tool in git python3 systemctl flock timeout; do
  command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
python3 -c 'import sys; sys.exit(sys.version_info < (3, 12))' || {
  echo "Python 3.12 or newer is required" >&2; exit 1;
}
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

# Refuse to back up a different DB from the service's EnvironmentFile.
if [[ -f "$ENV_FILE" ]]; then
  CONFIGURED_DB=$(sed -n 's/^X2_DB_PATH=//p' "$ENV_FILE" | tail -1)
  CONFIGURED_DB=${CONFIGURED_DB%$'\r'}
  CONFIGURED_DB=${CONFIGURED_DB#\"}; CONFIGURED_DB=${CONFIGURED_DB%\"}
  if [[ -n "$CONFIGURED_DB" && "$CONFIGURED_DB" != "$DB_PATH" ]]; then
    echo "DB path mismatch: set X2_DB_PATH=$CONFIGURED_DB to match $ENV_FILE" >&2
    exit 1
  fi
fi
mkdir -p "$(dirname "$DB_PATH")"
exec 9>"$DB_PATH.deploy.lock"
flock -n 9 || { echo "Another deployment holds $DB_PATH.deploy.lock" >&2; exit 1; }
phase update-code

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

phase verify-backup-tool
if [[ ! -f tools/deploy_backup.py ]]; then
  echo "Missing tools/deploy_backup.py; update the complete repository before deployment. Service has not been stopped." >&2
  false
fi

phase install-dependencies
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e .
mkdir -p runtime logs "$(dirname "$DB_PATH")" "$(dirname "$ENV_FILE")" "$UNIT_DIR"
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

phase stop-service
# Stop only after installation has succeeded; systemd closes its DB connections.
if "${SYSTEMCTL[@]}" cat x2server.service >/dev/null 2>&1; then
  timeout --foreground 120 "${SYSTEMCTL[@]}" stop x2server.service
  ACTIVE=$("${SYSTEMCTL[@]}" show x2server.service -p ActiveState --value)
  MAIN_PID=$("${SYSTEMCTL[@]}" show x2server.service -p MainPID --value)
  if [[ "$ACTIVE" != inactive && "$ACTIVE" != failed ]] || [[ "$MAIN_PID" != 0 ]]; then
    echo "Service has not stopped: state=$ACTIVE pid=$MAIN_PID; refusing backup" >&2
    false
  fi
fi

phase prepare-storage
if [[ "$(id -u)" == 0 ]]; then
  # Avoid traversing every historical backup/log on every update.
  chown "$SERVICE_USER:$SERVICE_USER" "$(dirname "$DB_PATH")" runtime logs
  for active_file in "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm" "$DB_PATH-journal"; do
    if [[ -e "$active_file" ]]; then chown "$SERVICE_USER:$SERVICE_USER" "$active_file"; fi
  done
fi

phase backup-and-verify
if [[ -f "$DB_PATH" ]]; then
  BACKUP="$DB_PATH.predeploy.$(date -u +%Y%m%dT%H%M%SZ).$$.bak"
  # Python has cooperative deadlines for SQLite work; timeout also bounds the
  # whole process. Kernel D-state I/O cannot be forcibly bounded by user space.
  timeout --foreground --kill-after=10 660 .venv/bin/python -u tools/deploy_backup.py \
    --source "$DB_PATH" --destination "$BACKUP" --timeout 600
else
  echo "No existing database; first installation has no archive to back up."
fi

phase install-service

sed -e "s|@SERVICE_USER@|$SERVICE_USER|g" \
    -e "s|@WORKDIR@|$ROOT|g" -e "s|@ENV_FILE@|$ENV_FILE|g" \
    -e "s|@INSTALL_TARGET@|$INSTALL_TARGET|g" \
    deploy/x2server.service > "$UNIT_DIR/x2server.service"
"${SYSTEMCTL[@]}" daemon-reload
"${SYSTEMCTL[@]}" enable x2server.service
phase start-service
"${SYSTEMCTL[@]}" start x2server.service

# Read non-secret listener ports from the private EnvironmentFile.
HTTP_PORT=$(sed -n 's/^X2_HTTP_PORT=//p' "$ENV_FILE" | tail -1)
GAME_PORT=$(sed -n 's/^X2_GAME_PORT=//p' "$ENV_FILE" | tail -1)
CHAT_PORT=$(sed -n 's/^X2_CHAT_PORT=//p' "$ENV_FILE" | tail -1)
HTTP_PORT=${HTTP_PORT:-18080}; GAME_PORT=${GAME_PORT:-29000}; CHAT_PORT=${CHAT_PORT:-29001}
phase health-check
HEALTH=0
for attempt in $(seq 1 30); do
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
  echo "Waiting for service ports (attempt $attempt/30)..."
  sleep 1
done
if [[ "$HEALTH" != 1 ]]; then
  echo "Service health check failed. PREVIOUS_COMMIT=$PREVIOUS_COMMIT" >&2
  "${SYSTEMCTL[@]}" status x2server.service --no-pager || true
  false
fi
phase complete
echo "Deployment healthy at commit $(git rev-parse HEAD)"
echo "Open inbound TCP ports: $HTTP_PORT (HTTP login), $GAME_PORT (game), $CHAT_PORT (chat)."
echo "Configure fenrirchen.com A/AAAA to this server. Firewall changes are not automatic."
