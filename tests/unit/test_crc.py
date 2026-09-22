from x2server.protocol.crc import body_crc32


def test_crc32_standard_vector() -> None:
    assert body_crc32(b"123456789") == 0xCBF43926


def test_crc32_empty_body() -> None:
    assert body_crc32(b"") == 0

