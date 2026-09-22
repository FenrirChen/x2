import asyncio
import json
import urllib.error
import urllib.request

from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.models import (
    BootstrapConfig,
    GameEndpoint,
    RecoveredBootstrapContract,
    RecoveredControlInfo,
    RecoveredServerAddressConfig,
    RecoveredWebGameConfig,
    ServerAddressEntry,
)
from x2server.bootstrap.service import BootstrapService, RecoveredBootstrapService
from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.config.settings import Settings


def make_server(port: int = 29000) -> BootstrapHTTPServer:
    config = BootstrapConfig(
        game_server=GameEndpoint("127.0.0.1", port),
        environment="test",
        client_version="2.4",
    )
    return BootstrapHTTPServer("127.0.0.1", 0, BootstrapService(config))


def test_local_identity_receives_form_body_over_http() -> None:
    async def scenario() -> None:
        service = LocalIdentityService(
            RecoveredBootstrapContract.local(Settings(), game_server_port=29000),
            account="lab", password="local")
        server = BootstrapHTTPServer("127.0.0.1", 0, service)
        await server.start()
        try:
            url = f"http://{server.bound_host}:{server.bound_port}/loginwithpw"
            status, _, body = await asyncio.to_thread(
                request, url, "POST", b"account=lab&password=local")
            assert status == 200
            assert json.loads(body)["code"] == "ok"
        finally:
            await server.stop()
    asyncio.run(scenario())


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


def test_recovered_contract_is_served_over_local_http() -> None:
    async def scenario() -> None:
        local_http = "http://127.0.0.1:18080"
        contract = RecoveredBootstrapContract(
            RecoveredWebGameConfig(
                service_app_id="x2-local-compat",
                pbs_server=local_http,
                login_server=local_http,
                account_server=local_http,
                esweb_server=local_http,
                lb_pbs_server=(local_http,),
                lb_login_server=(local_http,),
                lb_esweb_server=(local_http,),
                area_id="local",
            ),
            RecoveredServerAddressConfig((ServerAddressEntry("127.0.0.1", 32123),)),
        )
        server = BootstrapHTTPServer(
            "127.0.0.1", 0, RecoveredBootstrapService(contract)
        )
        await server.start()
        base = f"http://{server.bound_host}:{server.bound_port}"
        connect_info = await asyncio.to_thread(request, base + "/apply/connectInfo")
        address = await asyncio.to_thread(request, base + "/apply/address")
        control_info = await asyncio.to_thread(request, base + "/apply/controlInfo")
        assert connect_info[0] == 200
        assert address[0] == 200
        assert control_info[0] == 200
        assert RecoveredWebGameConfig.from_json_bytes(connect_info[2]).area_id == "local"
        endpoint = RecoveredServerAddressConfig.from_json_bytes(address[2]).endpoints[0]
        assert (endpoint.host, endpoint.port) == ("127.0.0.1", 32123)
        assert RecoveredControlInfo.from_json_bytes(control_info[2]) == RecoveredControlInfo()
        await server.stop()

    asyncio.run(scenario())
