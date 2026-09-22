import asyncio
import json
import urllib.error
import urllib.request

from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.models import BootstrapConfig, GameEndpoint
from x2server.bootstrap.service import BootstrapService


def make_server(port: int = 29000) -> BootstrapHTTPServer:
    config = BootstrapConfig(
        game_server=GameEndpoint("127.0.0.1", port),
        environment="test",
        client_version="2.4",
    )
    return BootstrapHTTPServer("127.0.0.1", 0, BootstrapService(config))


def request(
    url: str, method: str = "POST", body: bytes | None = None
) -> tuple[int, str, bytes]:
    request_body = (b"{}" if body is None else body) if method == "POST" else None
    req = urllib.request.Request(url, data=request_body, method=method)
    # Integration traffic must stay on localhost even when the host environment defines a proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=2.0) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), error.read()


def test_bootstrap_http_returns_nonempty_parseable_config() -> None:
    async def scenario() -> None:
        server = make_server(32123)
        await server.start()
        url = f"http://{server.bound_host}:{server.bound_port}/webgameconfig"
        status, content_type, body = await asyncio.to_thread(request, url)
        assert status == 200
        assert content_type == "application/json; charset=utf-8"
        assert body
        config = BootstrapConfig.from_json_bytes(body)
        assert config.game_server.port == 32123
        await server.stop()

    asyncio.run(scenario())


def test_bootstrap_unknown_path_and_method_are_explicit() -> None:
    async def scenario() -> None:
        server = make_server()
        await server.start()
        base = f"http://{server.bound_host}:{server.bound_port}"
        not_found = await asyncio.to_thread(request, base + "/unknown")
        wrong_method = await asyncio.to_thread(request, base + "/webgameconfig", "GET")
        assert not_found[0] == 404, not_found
        assert json.loads(not_found[2]) == {"error": "not_found"}
        assert wrong_method[0] == 405, wrong_method
        assert json.loads(wrong_method[2]) == {"error": "method_not_allowed"}
        await server.stop()

    asyncio.run(scenario())


def test_bootstrap_service_can_restart_cleanly() -> None:
    async def scenario() -> None:
        server = make_server()
        await server.start()
        first_port = server.bound_port
        assert first_port > 0
        await server.stop()
        await server.start()
        assert server.bound_port > 0
        await server.stop()

    asyncio.run(scenario())


def test_bootstrap_consumes_post_body_before_responding() -> None:
    async def scenario() -> None:
        server = make_server()
        await server.start()
        url = f"http://{server.bound_host}:{server.bound_port}/webgameconfig"
        normal = await asyncio.to_thread(request, url, "POST", b'{"ignored":true}')
        assert normal[0] == 200
        await server.stop()

    asyncio.run(scenario())
