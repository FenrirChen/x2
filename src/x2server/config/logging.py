"""Standard logging setup with safe protocol context defaults."""

from __future__ import annotations

import logging


class _ContextDefaults(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for name, default in (
            ("connection_id", "-"),
            ("message_id", "-"),
            ("message_name", "-"),
            ("request_id", "-"),
        ):
            if not hasattr(record, name):
                setattr(record, name, default)
        return True


def configure_logging(level: str = "INFO") -> None:
    """Configure concise logs without authentication payload fields."""
    handler = logging.StreamHandler()
    handler.addFilter(_ContextDefaults())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s "
            "connection=%(connection_id)s message=%(message_id)s/%(message_name)s "
            "request=%(request_id)s %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

