"""Verified deployment backup with bounded SQLite work and visible progress."""
from __future__ import annotations

import argparse
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import threading
import time


def backup_database(source, destination, *, timeout=600.0, interval=5.0, log=print):
    """Publish only a fully checked backup; never modify or replace the source."""
    if timeout <= 0 or interval <= 0:
        raise ValueError("timeout and interval must be positive")
    source = Path(source).resolve(strict=True)
    destination = Path(destination).absolute()
    if not source.is_file() or source == destination.resolve():
        raise ValueError("source must be a file and destination must differ")
    partial = destination.with_name(destination.name + ".partial")
    if destination.exists() or partial.exists():
        raise FileExistsError("backup destination or partial already exists")
    started = time.monotonic()
    deadline = started + timeout
    status = {"stage": "metadata", "remaining": None, "total": None}
    stopped = threading.Event()
    created = False

    def check_deadline():
        if time.monotonic() >= deadline:
            raise TimeoutError("deployment backup time limit exceeded")

    def heartbeat():
        while not stopped.wait(interval):
            log(f"BACKUP_PROGRESS stage={status['stage']} "
                f"remaining_pages={status['remaining']} total_pages={status['total']} "
                f"elapsed={time.monotonic() - started:.1f}s")

    def progress(code, remaining, total):
        status.update(remaining=remaining, total=total)
        check_deadline()

    worker = threading.Thread(target=heartbeat, name="deploy-backup-progress", daemon=True)
    worker.start()
    try:
        log(f"BACKUP_START source={source} bytes={source.stat().st_size} timeout={timeout:g}s")
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True,
                                    timeout=min(1.0, timeout))) as source_db:
            check_deadline()
            page_size = source_db.execute("PRAGMA page_size").fetchone()[0]
            pages = source_db.execute("PRAGMA page_count").fetchone()[0]
            journal = source_db.execute("PRAGMA journal_mode").fetchone()[0]
            log(f"BACKUP_METADATA journal={journal} pages={pages} page_size={page_size}")
            check_deadline()
            # Exclusive creation protects old backups, including interrupted runs.
            fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            os.close(fd)
            status['stage'] = 'copy'
            log("BACKUP_COPY_START pages_per_step=256")
            with closing(sqlite3.connect(partial)) as target:
                source_db.backup(target, pages=256, progress=progress, sleep=.1)
                check_deadline()
                status['stage'] = 'integrity_check'
                log(f"BACKUP_COPY_DONE elapsed={time.monotonic() - started:.1f}s")
                log("BACKUP_CHECK_START type=integrity_check")
                target.set_progress_handler(lambda: int(time.monotonic() >= deadline), 10000)
                rows = target.execute("PRAGMA integrity_check").fetchall()
                if rows != [("ok",)]:
                    raise sqlite3.DatabaseError("backup integrity_check failed")
                check_deadline()
                log(f"BACKUP_CHECK_OK elapsed={time.monotonic() - started:.1f}s")
        status['stage'] = 'publish'
        with partial.open('r+b') as fh:
            os.fsync(fh.fileno())
        check_deadline()
        # Same-directory hard link publishes atomically and refuses any existing name.
        os.link(partial, destination)
        partial.unlink()
        created = False
        if os.name == 'posix':
            fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        log(f"DB_BACKUP={destination}")
        log(f"BACKUP_DONE bytes={destination.stat().st_size} elapsed={time.monotonic() - started:.1f}s")
        return destination
    except sqlite3.OperationalError as exc:
        if time.monotonic() >= deadline:
            raise TimeoutError("deployment backup time limit exceeded") from exc
        raise
    finally:
        stopped.set()
        worker.join()
        # Only this invocation's unfinished output; source and older backups survive.
        if created:
            partial.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--timeout', type=float, default=600)
    args = parser.parse_args()
    try:
        backup_database(args.source, args.destination, timeout=args.timeout,
                        log=lambda message: print(message, flush=True))
    except (OSError, sqlite3.Error, ValueError, TimeoutError) as exc:
        print(f"BACKUP_FAILED type={type(exc).__name__}: {exc}", flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
