"""Safe environment-based settings; deployment secrets never belong here."""

from __future__ import annotations

import os
from dataclasses import dataclass

# TEMPORARY_COMPAT: defensive local limit, not a recovered original constant.
DEFAULT_MAX_PACKET_SIZE = 16 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class Settings:
    """Non-secret process settings used by later service milestones."""

    max_packet_size: int = DEFAULT_MAX_PACKET_SIZE
    log_level: str = "INFO"

    @classmethod
    def from_environment(cls) -> Settings:
        """Read non-secret overrides from explicit X2-prefixed variables."""
        max_packet_size = int(os.getenv("X2_MAX_PACKET_SIZE", str(DEFAULT_MAX_PACKET_SIZE)))
        if max_packet_size <= 0:
            raise ValueError("X2_MAX_PACKET_SIZE must be positive")
        return cls(max_packet_size=max_packet_size, log_level=os.getenv("X2_LOG_LEVEL", "INFO"))

