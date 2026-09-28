import pytest

from x2server.config.deployment import DeploymentEndpoints


def test_local_defaults_and_public_override(monkeypatch):
    for name in ("X2_BIND_HOST", "X2_PUBLIC_HOST", "X2_HTTP_PORT", "X2_GAME_PORT", "X2_CHAT_PORT"):
        monkeypatch.delenv(name, raising=False)
    assert DeploymentEndpoints.from_environment() == DeploymentEndpoints(
        "127.0.0.1", "10.0.2.2", 18080, 29000, 29001)
    monkeypatch.setenv("X2_BIND_HOST", "0.0.0.0")
    monkeypatch.setenv("X2_PUBLIC_HOST", "fenrirchen.com")
    assert DeploymentEndpoints.from_environment().public_host == "fenrirchen.com"


def test_rejects_invalid_ports_and_public_urls(monkeypatch):
    monkeypatch.setenv("X2_GAME_PORT", "0")
    with pytest.raises(ValueError):
        DeploymentEndpoints.from_environment()
    monkeypatch.setenv("X2_GAME_PORT", "29000")
    monkeypatch.setenv("X2_PUBLIC_HOST", "http://fenrirchen.com")
    with pytest.raises(ValueError):
        DeploymentEndpoints.from_environment()
