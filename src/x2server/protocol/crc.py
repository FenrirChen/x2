"""Request-body checksum support."""

import zlib


def body_crc32(body: bytes) -> int:
    """Return the unsigned CRC32 stored in request-header ``sign``.

    This checksum is not the independent fight-session ``sign`` value.
    """
    return zlib.crc32(body) & 0xFFFFFFFF

