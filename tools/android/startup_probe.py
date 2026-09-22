"""Observe an already cold-booted Revival lab; never install or clear app data.

Run from the repository root with ``python -m tools.android.startup_probe``.
Raw logs, screenshots and command results stay in an ignored runtime directory.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from x2server.bootstrap.http_server import BootstrapHTTPServer
from x2server.bootstrap.models import RecoveredBootstrapContract
from x2server.bootstrap.service import HTTPResponse, RecoveredBootstrapService
from x2server.config.settings import Settings

PACKAGE = "com.siva.project.x2"
AVD = "X2-ABI-Probe-API30"
REVIVAL_HASH = "b6a95c274cd61a91d2c4ab1ea448a300669bbc91861e989c1593da8dd071f98f"


def startup_healthy(result: dict[str, Any]) -> bool:
    """HTTP contact alone is insufficient: a pink screen or dead client must fail."""
    return bool(result.get("bootstrap_reached") and result.get("awake") and
                result.get("main_process_alive") and not result.get("error") and
                not result.get("memory_16gb_error") and
                not result.get("shader_platform_error"))


def warning_button(xml: str) -> tuple[int, int] | None:
    """Only acknowledge the observed Unity hardware warning, never another dialog."""
    root = ET.fromstring(xml)
    nodes = list(root.iter("node"))
    if not any("Your device does not match the hardware requirements" in
               node.get("text", "") for node in nodes):
        return None
    for node in nodes:
        if (node.get("package") == PACKAGE and
                node.get("resource-id") == "android:id/button1" and
                node.get("text", "").lower() == "continue"):
            match = re.fullmatch(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", node.get("bounds", ""))
            if match:
                left, top, right, bottom = map(int, match.groups())
                return (left + right) // 2, (top + bottom) // 2
    return None


class Observer(RecoveredBootstrapService):
    def __init__(self) -> None:
        super().__init__(RecoveredBootstrapContract.local(Settings(
            bootstrap_host="10.0.2.2", bootstrap_port=18080,
            game_server_host="10.0.2.2", game_server_port=29000,
        )))
        self.hits: list[dict[str, Any]] = []

    def respond(self, method: str, target: str) -> HTTPResponse:
        response = super().respond(method, target)
        self.hits.append({"method": method, "path": target.split("?", 1)[0],
                          "status": response.status})
        return response


async def observe(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    runtime = Path(__file__).resolve().parents[2] / "runtime"
    if not output.is_relative_to(runtime):
        raise ValueError("Output must be inside the repository runtime directory")
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {"started_utc": datetime.now(timezone.utc).isoformat(),
                              "serial": args.serial, "avd": AVD,
                              "duration_seconds": args.seconds,
                              "bootstrap_reached": False, "error": None}
    result["probe_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def adb(*command: str, required: bool = True, timeout: float = 30) -> str:
        process = subprocess.run([str(args.adb), "-s", args.serial, *command],
                                 capture_output=True, timeout=timeout, check=False)
        text = (process.stdout + process.stderr).decode("utf-8", errors="replace")
        if required and process.returncode:
            raise RuntimeError(f"ADB {command[:2]} failed: {text[:250]}")
        return text.strip()

    observer = Observer()
    server = BootstrapHTTPServer("127.0.0.1", 18080, observer)
    try:
        name = await asyncio.to_thread(adb, "emu", "avd", "name")
        if name.splitlines()[0] != AVD:
            raise RuntimeError("Unexpected AVD; refusing to launch")
        if await asyncio.to_thread(adb, "shell", "getprop", "sys.boot_completed") != "1":
            raise RuntimeError("Android has not completed boot")
        if await asyncio.to_thread(adb, "shell", "id", "-u") != "0":
            raise RuntimeError("Run adb root on the disposable lab first")
        package = await asyncio.to_thread(adb, "shell", "dumpsys", "package", PACKAGE)
        result["package_metadata"] = [line.strip() for line in package.splitlines()
                                      if any(key in line for key in
                                             ("primaryCpuAbi=", "versionCode=", "versionName="))]
        apk = await asyncio.to_thread(adb, "shell", "pm", "path", PACKAGE)
        if not apk.startswith("package:") or len(apk.splitlines()) != 1:
            raise RuntimeError("Expected exactly one installed APK")
        installed_hash = (await asyncio.to_thread(
            adb, "shell", "sha256sum", apk[8:], timeout=120
        )).split()[0]
        result["installed_apk_sha256"] = installed_hash
        if installed_hash != REVIVAL_HASH:
            raise RuntimeError("Installed APK is not the frozen Revival v0.1 baseline")
        result["gles_version"] = await asyncio.to_thread(adb, "shell", "getprop", "ro.opengles.version")
        result["guest_http_proxy"] = await asyncio.to_thread(
            adb, "shell", "settings", "get", "global", "http_proxy")
        await server.start()
        await asyncio.to_thread(adb, "shell", "am", "force-stop", PACKAGE)
        await asyncio.to_thread(adb, "logcat", "-c")
        result["launch"] = await asyncio.to_thread(
            adb, "shell", "am", "start", "-W", "-n", f"{PACKAGE}/{PACKAGE}.X2UnityActivity")
        deadline = time.monotonic() + args.seconds
        acknowledged = False
        while time.monotonic() < deadline:
            await asyncio.sleep(5)
            dumped = await asyncio.to_thread(adb, "shell", "uiautomator", "dump",
                                            "/data/local/tmp/x2-startup.xml", required=False)
            if "dumped to:" not in dumped:
                continue  # Never act on a stale XML file from a previous observation.
            xml = await asyncio.to_thread(adb, "shell", "cat", "/data/local/tmp/x2-startup.xml",
                                          required=False)
            (output / "ui.xml").write_text(xml, encoding="utf-8")
            try:
                button = warning_button(xml)
            except ET.ParseError:
                button = None
            if button and not acknowledged:
                await asyncio.to_thread(adb, "shell", "input", "tap", *map(str, button))
                acknowledged = True
        result["hardware_warning_acknowledged"] = acknowledged
        log = await asyncio.to_thread(adb, "logcat", "-d")
        (output / "logcat.log").write_text(log, encoding="utf-8")
        result["awake"] = "AppMainImpl:Awake" in log
        result["memory_16gb_error"] = "Using memoryadresses from more that 16GB" in log
        result["shader_platform_error"] = "Desired shader compiler platform" in log
        result["main_process_alive"] = bool(await asyncio.to_thread(
            adb, "shell", "pidof", PACKAGE, required=False))
        await asyncio.to_thread(adb, "shell", "screencap", "-p", "/data/local/tmp/x2-startup.png")
        await asyncio.to_thread(adb, "pull", "/data/local/tmp/x2-startup.png", str(output / "screen.png"))
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        await server.stop()
        result["http_hits"] = observer.hits
        result["bootstrap_reached"] = any(hit["status"] == 200 and
                                          hit["path"] == "/apply/controlInfo" and
                                          hit["method"] == "POST" for hit in observer.hits)
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        result["startup_healthy"] = startup_healthy(result)
        result["artifacts_sha256"] = {
            file.name: hashlib.sha256(file.read_bytes()).hexdigest()
            for file in output.iterdir() if file.is_file()
        }
        (output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2), flush=True)
    return 0 if result["startup_healthy"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adb", type=Path, required=True)
    parser.add_argument("--serial", default="emulator-5554")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=60)
    args = parser.parse_args()
    if not 15 <= args.seconds <= 180:
        parser.error("--seconds must be between 15 and 180")
    return asyncio.run(observe(args))


if __name__ == "__main__":
    raise SystemExit(main())
