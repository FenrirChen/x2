"""Execute the actual Bash deploy script with isolated command doubles."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[2]


def shell_path(path):
    text = Path(path).resolve().as_posix()
    return '/' + text[0].lower() + text[2:] if os.name == 'nt' else text


def bash_binary():
    if os.name == 'nt':
        git = shutil.which('git')
        candidate = Path(git).parents[1] / 'bin/bash.exe' if git else Path('missing')
        if candidate.is_file():
            return str(candidate)
    elif shutil.which('bash'):
        return shutil.which('bash')
    pytest.skip('Bash is required for deployment orchestration regression')


STUB = r"""#!/usr/bin/env bash
set -e
name=$(basename "$0")
printf '%s %s\n' "$name" "$*" >> "$HARNESS_EVENTS"
case "$name" in
  id) if [[ "$1" == -u ]]; then echo 1000; else echo tester; fi ;;
  flock) [[ "${TEST_LOCK_BUSY:-0}" != 1 ]] ;;
  timeout)
    while [[ "$1" == --* ]]; do shift; done
    shift
    exec "$@"
    ;;
  git)
    case "$*" in
      'remote get-url origin') echo https://github.com/FenrirChen/x2.git ;;
      'branch --show-current') echo main ;;
      'status --porcelain') if [[ "${TEST_DIRTY:-0}" == 1 ]]; then echo ' M local-change'; fi ;;
      'rev-parse HEAD') echo abc123 ;;
    esac
    ;;
  python3)
    if [[ "$1" == - && "${TEST_HEALTH_FAILED:-0}" == 1 ]]; then exit 1; fi
    ;;
  sleep) : ;;
  python)
    if [[ "$*" == *'pip install -e'* && "${TEST_INSTALL_FAILED:-0}" == 1 ]]; then exit 4; fi
    if [[ "$*" == *'tools/deploy_backup.py'* ]]; then
      if [[ -f "$HARNESS_STATE" && "$(cat "$HARNESS_STATE")" == running ]]; then
        echo 'ERROR backup ran before service stopped'; exit 99
      fi
      if [[ "${TEST_BACKUP_INTERRUPTED:-0}" == 1 ]]; then kill -TERM "$PPID"; exit 143; fi
      if [[ "${TEST_BACKUP_FAILED:-0}" == 1 ]]; then exit 9; fi
      while [[ "$1" != --destination ]]; do shift; done
      printf 'verified fake backup' > "$2"
      echo "DB_BACKUP=$2"
    fi
    ;;
  systemctl)
    if [[ "$1" == --user ]]; then shift; fi
    case "$1" in
      cat) [[ "${TEST_NEW_INSTALL:-0}" != 1 ]] ;;
      stop)
        if [[ "${TEST_STOP_FAILED:-0}" == 1 ]]; then exit 5; fi
        if [[ "${TEST_STOP_STUCK:-0}" != 1 ]]; then echo stopped > "$HARNESS_STATE"; fi
        ;;
      show)
        if [[ "$*" == *ActiveState* ]]; then
          if [[ "$(cat "$HARNESS_STATE")" == running ]]; then echo active; else echo inactive; fi
        else
          if [[ "$(cat "$HARNESS_STATE")" == running ]]; then echo 77; else echo 0; fi
        fi
        ;;
      start) if [[ "${TEST_START_FAILED:-0}" == 1 ]]; then exit 7; fi; echo running > "$HARNESS_STATE" ;;
      is-active) [[ "$(cat "$HARNESS_STATE")" == running ]] ;;
    esac
    ;;
esac
exit 0
"""


def execute(tmp_path, **flags):
    base = tmp_path
    root = base / 'repo'
    home = base / 'home'
    envfile = base / 'server.env'
    db = base / 'data/player.sqlite3'
    events = base / 'events'
    state = base / 'service-state'
    stubs = base / 'commands'
    for directory in (root / '.git', root / '.venv/bin', root / 'deploy', root / 'tools', home, db.parent, stubs):
        directory.mkdir(parents=True, exist_ok=True)
    if not flags.get('TEST_HELPER_MISSING'):
        (root / 'tools/deploy_backup.py').write_text('# backup tool fixture\n')
    db.write_bytes(b'live player save - must survive')
    old_backup = db.with_name('historical.bak')
    old_backup.write_bytes(b'old verified archive')
    shutil.copyfile(REPO / 'deploy/x2server.service', root / 'deploy/x2server.service')
    for name in ('id', 'flock', 'timeout', 'git', 'python3', 'systemctl', 'sleep'):
        stub = stubs / name
        stub.write_text(STUB, encoding='utf-8', newline='\n')
        stub.chmod(0o755)
    python = root / '.venv/bin/python'
    python.write_text(STUB, encoding='utf-8', newline='\n')
    python.chmod(0o755)
    envfile.write_text('X2_DB_PATH=' + (shell_path(base / 'wrong.sqlite3') if flags.get('TEST_DB_MISMATCH') else shell_path(db)) + '\n')
    if not flags.get('TEST_NEW_INSTALL'):
        state.write_text('stopped' if flags.get('TEST_INITIALLY_STOPPED') else 'running')
    env = os.environ.copy()
    env.update({
        'X2_HEALTH_ATTEMPTS': '3',
        'HOME': shell_path(home), 'X2_DEPLOY_ROOT': shell_path(root),
        'X2_DB_PATH': shell_path(db), 'X2_ENV_FILE': shell_path(envfile),
        'HARNESS_BIN': shell_path(stubs), 'HARNESS_EVENTS': shell_path(events),
        'HARNESS_STATE': shell_path(state),
        'SCRIPT_UNDER_TEST': shell_path(REPO / 'deploy/deploy_server.sh'),
        **{key: str(value) for key, value in flags.items()},
    })
    result = subprocess.run([bash_binary(), '--noprofile', '--norc', '-c',
        'export PATH="$HARNESS_BIN:/usr/bin:/bin"; exec bash "$SCRIPT_UNDER_TEST"'],
        env=env, cwd=base, capture_output=True, text=True, timeout=30)
    assert db.read_bytes() == b'live player save - must survive'
    assert old_backup.read_bytes() == b'old verified archive'
    return result, events.read_text() if events.exists() else '', state


def test_actual_deploy_script_installs_then_stops_backs_up_and_starts(tmp_path):
    result, events, state = execute(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert events.index('pip install -e .') < events.index('systemctl --user stop')
    assert events.index('systemctl --user stop') < events.index('python -u tools/deploy_backup.py')
    assert events.index('python -u tools/deploy_backup.py') < events.index('systemctl --user start')
    assert state.read_text().strip() == 'running'
    assert 'Deployment healthy' in result.stdout


@pytest.mark.parametrize('flag', ('TEST_BACKUP_FAILED', 'TEST_STOP_FAILED', 'TEST_STOP_STUCK', 'TEST_BACKUP_INTERRUPTED'))
def test_stop_or_backup_failure_restores_previously_running_service(tmp_path, flag):
    result, events, state = execute(tmp_path, **{flag: 1})
    assert result.returncode != 0
    assert 'systemctl --user start' in events
    assert 'Deployment healthy' not in result.stdout
    assert state.read_text().strip() == 'running'
    assert 'RECOVERY_OK' in result.stderr
    if flag in ('TEST_STOP_FAILED', 'TEST_STOP_STUCK'):
        assert 'python -u tools/deploy_backup.py' not in events
    else:
        assert 'stage=backup-and-verify' in result.stderr


@pytest.mark.parametrize('flag', ['TEST_INITIALLY_STOPPED', 'TEST_NEW_INSTALL'])
def test_backup_failure_does_not_start_intentionally_stopped_or_missing_service(tmp_path, flag):
    result, events, state = execute(tmp_path, TEST_BACKUP_FAILED=1, **{flag:1})
    assert result.returncode != 0
    assert 'systemctl --user start' not in events
    assert 'RECOVERY_START' not in result.stderr
    assert not state.exists() or state.read_text().strip() == 'stopped'


def test_recovery_start_failure_is_visible_and_keeps_original_error(tmp_path):
    result, events, state = execute(tmp_path, TEST_BACKUP_FAILED=1, TEST_START_FAILED=1)
    assert result.returncode == 9
    assert state.read_text().strip() == 'stopped'
    assert 'RECOVERY_FAILED' in result.stderr and 'RECOVERY_OK' not in result.stderr
    assert 'systemctl --user status' in events


def test_recovery_checks_ports_and_does_not_confuse_running_with_healthy(tmp_path):
    result, _, state = execute(tmp_path, TEST_BACKUP_FAILED=1, TEST_HEALTH_FAILED=1)
    assert result.returncode == 9
    assert state.read_text().strip() == 'running'
    assert 'RECOVERY_FAILED' in result.stderr and 'RECOVERY_OK' not in result.stderr


def test_default_and_explicit_backup_policy_are_forwarded(tmp_path):
    result, events, _ = execute(tmp_path)
    assert result.returncode == 0
    assert '--timeout 1800 --check quick_check' in events
    result, events, _ = execute(tmp_path / 'full', X2_BACKUP_TIMEOUT=3600, X2_BACKUP_CHECK='integrity_check')
    assert result.returncode == 0
    assert '--timeout 3600 --check integrity_check' in events
    assert 'timeout --foreground --kill-after=10 3660' in events


@pytest.mark.parametrize('flags', [dict(X2_BACKUP_TIMEOUT='0'), dict(X2_BACKUP_TIMEOUT='bad'), dict(X2_BACKUP_CHECK='invalid')])
def test_bad_backup_settings_rejected_before_stopping_service(tmp_path, flags):
    result, events, state = execute(tmp_path, **flags)
    assert result.returncode != 0
    assert 'systemctl --user stop' not in events
    assert state.read_text() == 'running'


@pytest.mark.parametrize('flag', ('TEST_LOCK_BUSY', 'TEST_DB_MISMATCH', 'TEST_DIRTY', 'TEST_INSTALL_FAILED', 'TEST_HELPER_MISSING'))
def test_preflight_and_install_failure_leave_existing_service_running(tmp_path, flag):
    result, events, state = execute(tmp_path, **{flag: 1})
    assert result.returncode != 0
    assert 'systemctl --user stop' not in events
    assert 'python -u tools/deploy_backup.py' not in events
    assert state.read_text().strip() == 'running'


def test_first_install_without_existing_unit_can_complete(tmp_path):
    result, events, state = execute(tmp_path, TEST_NEW_INSTALL=1)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'systemctl --user stop' not in events
    assert state.read_text().strip() == 'running'


def test_failed_health_check_reports_attempts_and_does_not_claim_success(tmp_path):
    result, events, state = execute(tmp_path, TEST_HEALTH_FAILED=1)
    assert result.returncode != 0
    assert 'attempt 1/3' in result.stdout
    assert 'attempt 3/3' in result.stdout
    assert 'Deployment healthy' not in result.stdout
    assert 'stage=health-check' in result.stderr
    assert 'systemctl --user status' in events
