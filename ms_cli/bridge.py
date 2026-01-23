"""
Bridge process management.
"""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from .platform import is_windows


Transport = Literal["udp", "ws"]


@dataclass
class BridgeConfig:
    """Bridge startup configuration."""

    transport: Transport
    controller_port: int
    host_port: int


class Bridge:
    """Manages the oc-bridge process lifecycle."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self._process: Optional[subprocess.Popen] = None

    def start(self, config: BridgeConfig) -> bool:
        """Start bridge in background."""
        exe = self._find_executable()
        if not exe:
            return False

        self._process = subprocess.Popen(
            [
                str(exe),
                "--headless",
                "--controller",
                config.transport,
                "--controller-port",
                str(config.controller_port),
                "--udp-port",
                str(config.host_port),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        time.sleep(0.3)
        return self._process.poll() is None

    def stop(self) -> None:
        """Stop bridge process."""
        if self._process is None:
            return

        self._process.terminate()
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        self._process = None

    def is_running(self) -> bool:
        """Check if bridge is running."""
        if self._process is None:
            return False
        return self._process.poll() is None

    def _find_executable(self) -> Optional[Path]:
        """Find bridge executable."""
        name = "oc-bridge.exe" if is_windows() else "oc-bridge"

        # Prefer workspace-installed binary (stable path)
        exe = self.workspace / "bin" / "bridge" / name
        if exe.exists():
            return exe

        # Fall back to build output
        exe = self.workspace / "open-control" / "bridge" / "target" / "release" / name
        if exe.exists():
            return exe

        return None


def extract_controller_port(source_file: Path, transport: Transport) -> Optional[int]:
    """Extract controller port from C++ source file."""
    if not source_file.exists():
        return None

    content = source_file.read_text(encoding="utf-8", errors="ignore")

    if transport == "udp":
        match = re.search(r"\.port\s*=\s*(\d+)", content)
    else:
        match = re.search(r"localhost:(\d+)", content)

    return int(match.group(1)) if match else None


def get_bridge_config(
    codebase_path: Path, target: Literal["native", "wasm"]
) -> Optional[BridgeConfig]:
    """Get bridge configuration for a codebase and target."""
    host_ports = {"native": 9001, "wasm": 9002}

    if target == "native":
        source = codebase_path / "sdl" / "main-native.cpp"
        transport: Transport = "udp"
    else:
        source = codebase_path / "sdl" / "main-wasm.cpp"
        transport = "ws"

    ctrl_port = extract_controller_port(source, transport)
    if ctrl_port is None:
        return None

    return BridgeConfig(
        transport=transport,
        controller_port=ctrl_port,
        host_port=host_ports[target],
    )
