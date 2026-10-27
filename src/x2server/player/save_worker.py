"""Short-lived save worker: heavy archive work never shares the game GIL/heap.

Only the trusted local parent supplies paths over stdin. JSON control messages
carry no archive contents. The parent owns the import barrier and checkpoint
file lock from write_begin through write_end (or confirmed child termination).
"""
from contextlib import contextmanager
import json
import logging
import os
import threading
from pathlib import Path
import sys

from .save_manager import SaveManager, AccountOnlineError
from .save_limits import SaveLimits


def emit(value):
    print(json.dumps(value), flush=True)


class WorkerStore:
    def __init__(self, path):
        self.path = Path(path)

    @contextmanager
    def import_write(self):
        emit({'event': 'write_begin'})
        try:
            answer = json.loads(sys.stdin.readline())
            if not answer.get('allow'):
                raise AccountOnlineError('account became online before import')
            # If the supervising server disappears, stop the writer too. Use
            # os.read rather than buffered stdin in a daemon (safe shutdown).
            def watch_parent():
                os.read(sys.stdin.fileno(), 1)
                os._exit(70)
            threading.Thread(target=watch_parent, name='save-parent-watch', daemon=True).start()
            yield
        finally:
            emit({'event': 'write_end'})


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format='%(asctime)s %(levelname)s %(name)s %(message)s')
    request = json.loads(sys.stdin.readline())
    manager = SaveManager(WorkerStore(request['database']), Path(request['backup_root']))
    try:
        if request['operation'] == 'export':
            Path(request['output']).write_bytes(manager.export_save(request['player']))
            emit({'event': 'done'})
        elif request['operation'] == 'import':
            limits = SaveLimits(**request['limits']) if request.get('limits') else None
            result = manager.import_save(request['player'], Path(request['input']).read_bytes(),
                                         actor=request['actor'], limits=limits)
            emit({'event': 'done', 'result': result})
        else:
            raise ValueError('unknown save worker operation')
    except Exception as exc:
        logging.getLogger('x2.save_worker').exception('save worker operation failed')
        result = {'event': 'error', 'type': type(exc).__name__, 'message': str(exc)}
        if hasattr(exc, 'retry_after'):
            result['retry_after'] = exc.retry_after
        emit(result)
    finally:
        manager.close()


if __name__ == '__main__':
    main()
