"""Run one bounded Revival Client First Contact observation."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.local_identity import LocalIdentityService
from x2server.bootstrap.models import (
    RecoveredBootstrapContract,
    RecoveredControlInfo,
    RecoveredServerAddressConfig,
    RecoveredWebGameConfig,
    ServerAddressEntry,
)
from x2server.bootstrap.service import HTTPResponse, RecoveredBootstrapService
from x2server.config.logging import configure_logging
from x2server.config.settings import Settings
from x2server.messages.core import CORE_SCHEMAS
from x2server.network.dispatcher import DispatchContext, Dispatcher
from x2server.network.server import X2TCPServer
from x2server.protocol.types import DecodedPacket

LOGGER = logging.getLogger("x2.first_contact")


@dataclass
class FirstContactResult:
    control_info: bool = False
    connect_info: bool = False
    address: bool = False
    tcp_connected: bool = False
    frame_decoded: bool = False
    first_message_id: int | None = None
    first_message_name: str | None = None
    crc: str = "N/A"
    protobuf: str = "N/A"
    body_sha256: str | None = None
    local_identity_valid: bool | None = None
    field_metadata: dict[str, dict[str, Any]] | None = None
    highest_fc: str = "below FC0"
    error: str | None = None


class ObservedBootstrapService:
    def __init__(self, inner: RecoveredBootstrapService, result: FirstContactResult) -> None:
        self.inner = inner
        self.result = result

    def respond(self, method: str, target: str, body: bytes = b"") -> HTTPResponse:
        path = target.split("?", 1)[0]
        if method.upper() == "POST" and path == self.inner.CONTROL_INFO_PATH:
            self.result.control_info = True
            self.result.highest_fc = "FC0"
            LOGGER.info("/apply/controlInfo hit")
        elif method.upper() == "POST" and path == self.inner.CONNECT_INFO_PATH:
            self.result.connect_info = True
            self.result.highest_fc = "FC1"
            LOGGER.info("FC1 /apply/connectInfo hit")
        elif method.upper() == "POST" and path == self.inner.SERVER_ADDRESS_PATH:
            self.result.address = True
            self.result.highest_fc = "FC2"
            LOGGER.info("FC2 /apply/address hit")
        return self.inner.respond(method, target, body)


def safe_field_metadata(values: dict[str, Any]) -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    for name, value in values.items():
        item: dict[str, Any] = {"present": True, "type": type(value).__name__}
        if isinstance(value, (str, bytes, bytearray)):
            item["length"] = len(value)
        metadata[name] = item
    return metadata


async def run(result_path: Path, timeout: float, control_update: str = "", local_account: bool = False) -> FirstContactResult:
    result = FirstContactResult()
    login_seen = asyncio.Event()

    async def observe_login(context: DispatchContext, packet: DecodedPacket) -> None:
        result.tcp_connected = True
        result.frame_decoded = True
        result.first_message_id = packet.message_id
        result.first_message_name = "C2L_Login"
        result.crc = "valid"  # PacketStreamDecoder verifies CRC before dispatch.
        values = CORE_SCHEMAS["C2L_Login"].decode(packet.body)
        result.protobuf = "decoded"
        result.body_sha256 = hashlib.sha256(packet.body).hexdigest()
        if isinstance(inner, LocalIdentityService):
            result.local_identity_valid = inner.validates_game_identity(
                values.get("id", 0), values.get("token", ""))
        result.field_metadata = safe_field_metadata(values)
        result.highest_fc = "FC5-LOGIN"
        LOGGER.info(
            "FC5-LOGIN decoded; fields=%s; values redacted; no response",
            json.dumps(result.field_metadata, sort_keys=True),
            extra={
                "connection_id": context.connection_id,
                "peer": context.peer,
                "message_id": packet.message_id,
                "message_name": "C2L_Login",
                "request_id": packet.header.request_id,
            },
        )
        login_seen.set()
        return None

    guest_http = "http://10.0.2.2:18080"
    contract = RecoveredBootstrapContract(
        RecoveredWebGameConfig(
            service_app_id="x2-local-compat",
            pbs_server=guest_http,
            login_server=guest_http,
            account_server=guest_http,
            esweb_server=guest_http,
            lb_pbs_server=(guest_http,),
            lb_login_server=(guest_http,),
            lb_esweb_server=(guest_http,),
            area_id="local",
        ),
        RecoveredServerAddressConfig(
            (ServerAddressEntry("10.0.2.2", 29000, description="Revival local"),)
        ),
    )
    inner = (LocalIdentityService(contract, account=os.environ["X2_LOCAL_ACCOUNT"],
                                 password=os.environ["X2_LOCAL_PASSWORD"])
             if local_account else RecoveredBootstrapService(
                 contract, RecoveredControlInfo(update=control_update)))
    service = ObservedBootstrapService(inner, result)
    bootstrap = BootstrapHTTPServer("127.0.0.1", 18080, service)  # type: ignore[arg-type]
    tcp = X2TCPServer(
        Settings(tcp_host="127.0.0.1", tcp_port=29000),
        Dispatcher({"C2L_Login": observe_login}),
    )

    try:
        await tcp.start()
        await bootstrap.start()
        LOGGER.info("services ready bootstrap=127.0.0.1:18080 tcp=127.0.0.1:29000")

        async def observe_tcp() -> None:
            while not login_seen.is_set():
                if tcp.active_connection_count and not result.tcp_connected:
                    result.tcp_connected = True
                    result.highest_fc = "FC3"
                    LOGGER.info("FC3 TCP client connected")
                await asyncio.sleep(0.05)

        observer = asyncio.create_task(observe_tcp())
        try:
            async with asyncio.timeout(timeout):
                await login_seen.wait()
        except TimeoutError:
            LOGGER.warning("First Contact timeout after %.1f seconds", timeout)
        finally:
            observer.cancel()
            await asyncio.gather(observer, return_exceptions=True)
    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"
        LOGGER.exception("First Contact runner failed")
    finally:
        await bootstrap.stop()
        await tcp.stop()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--control-update", choices=("", "LEBIAN", "TAPTAP"), default="")
    parser.add_argument("--local-account", action="store_true", help="Use X2_LOCAL_ACCOUNT and X2_LOCAL_PASSWORD for the temporary local identity bridge")
    args = parser.parse_args()
    configure_logging("INFO")
    result = asyncio.run(run(args.result, args.timeout, args.control_update, args.local_account))
    print(json.dumps(asdict(result), sort_keys=True))
    return 0 if result.highest_fc == "FC5-LOGIN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
