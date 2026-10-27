"""Bounded subprocess bridge for the HTTP save-manager surface."""
from contextlib import ExitStack
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from .save_manager import AccountOnlineError, SaveBoundaryError
from .save_limits import SaveCooldownError


class SaveJobError(RuntimeError):
    pass


class SaveJobRunner:
    def __init__(self, store, backup_root, timeout=180):
        self.store, self.backup_root, self.timeout = store, Path(backup_root), timeout
        self._condition = threading.Condition()
        self._closing = False
        self._running = 0
        self._processes = set()

    def run(self, *args, **kwargs):
        with self._condition:
            if self._closing:
                raise SaveJobError('save worker service is stopping')
            self._running += 1
        try:
            return self._run(*args, **kwargs)
        finally:
            with self._condition:
                self._running -= 1
                self._condition.notify_all()

    def close(self):
        # Called off the game loop: pending online checks can still complete.
        # Never close SQLite/guards while an HTTP job still owns its barrier.
        with self._condition:
            self._closing = True
            for proc in tuple(self._processes):
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except OSError:
                        pass
            while self._running:
                self._condition.wait()

    def _run(self, operation, player, data=None, *, actor='save-manager', offline_check=None, limits=None):
        with tempfile.TemporaryDirectory(prefix='x2-save-job-') as directory:
            root = Path(directory)
            request = {'operation': operation, 'player': player,
                       'database': str(self.store.path.resolve()),
                       'backup_root': str(self.backup_root.resolve()),
                       'input': str(root / 'input.x2save'), 'output': str(root / 'output.x2save'),
                       'actor': actor, 'limits': asdict(limits) if limits else None}
            if data is not None:
                (root / 'input.x2save').write_bytes(data)
            options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            env = dict(os.environ)
            # Use the exact package running the server, including source checkouts.
            package_root = str(Path(__file__).resolve().parents[2])
            env['PYTHONPATH'] = os.pathsep.join(filter(None, (package_root, str(Path(sys.prefix) / 'Lib' / 'site-packages') if os.name == 'nt' else '', env.get('PYTHONPATH', ''))))
            env['PYTHONIOENCODING'] = 'utf-8'
            with self._condition:
                if self._closing:
                    raise SaveJobError('save worker service is stopping')
                proc = subprocess.Popen([getattr(sys, '_base_executable', sys.executable) if os.name == 'nt' else sys.executable, '-B', '-m', 'x2server.player.save_worker'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        text=True, encoding='utf-8', env=env, **options)
                self._processes.add(proc)
            expired = threading.Event()
            def timeout():
                expired.set()
                try:
                    proc.kill()
                except OSError:
                    pass
            timer = threading.Timer(self.timeout, timeout)
            timer.daemon = True
            timer.start()
            # Keep the barrier until the worker is gone even on protocol/timeout
            # failure. A killed SQLite writer rolls back before the next writer.
            with ExitStack() as barrier:
                try:
                    proc.stdin.write(json.dumps(request) + '\n'); proc.stdin.flush()
                    active = False
                    result = None
                    for line in proc.stdout:
                        message = json.loads(line)
                        event = message.get('event')
                        if event == 'write_begin':
                            if operation != 'import' or active:
                                raise SaveJobError('invalid save worker barrier')
                            barrier.enter_context(self.store.import_write())
                            active = True
                            allow = offline_check is None or offline_check()
                            proc.stdin.write(json.dumps({'allow': allow}) + '\n'); proc.stdin.flush()
                        elif event == 'write_end':
                            if not active:
                                raise SaveJobError('unbalanced save worker barrier')
                            active = False
                            barrier.close()
                        elif event == 'error':
                            if message['type'] == 'SaveCooldownError':
                                raise SaveCooldownError(message['retry_after'])
                            errors = {'ValueError': ValueError, 'AccountOnlineError': AccountOnlineError,
                                      'SaveBoundaryError': SaveBoundaryError, 'KeyError': KeyError,
                                      'OSError': OSError, 'PermissionError': PermissionError}
                            raise errors.get(message['type'], SaveJobError)(message['message'])
                        elif event == 'done':
                            if active or result is not None:
                                raise SaveJobError('invalid save worker completion')
                            result = message
                        else:
                            raise SaveJobError('unknown save worker message')
                    if proc.wait() != 0 or result is None or expired.is_set():
                        raise SaveJobError('save worker failed or timed out')
                    if operation == 'export':
                        return (root / 'output.x2save').read_bytes()
                    return result['result']
                finally:
                    timer.cancel()
                    if proc.poll() is None:
                        proc.kill()
                    proc.wait()
                    proc.stdin.close()
                    proc.stdout.close()
                    with self._condition:
                        self._processes.discard(proc)
