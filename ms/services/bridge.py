from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ms.core.errors import ErrorCode
from ms.core.config import Config
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import PlatformInfo


class BridgeService:
    def __init__(
        self,
        *,
        workspace: Workspace,
        platform: PlatformInfo,
        config: Config | None,
        console: ConsoleProtocol,
    ) -> None:
        self._workspace = workspace
        self._platform = platform
        self._config = config
        self._console = console

    def build(self, *, release: bool = True, dry_run: bool = False) -> bool:
        bridge_dir = self._bridge_dir()
        if not bridge_dir.is_dir():
            self._console.error(f"bridge dir missing: {bridge_dir}")
            self._console.print("hint: Run: uv run ms repos sync", Style.DIM)
            return False

        if shutil.which("cargo") is None:
            self._console.error("cargo: missing")
            self._console.print("hint: install rustup: https://rustup.rs", Style.DIM)
            return False

        cmd = ["cargo", "build"]
        if release:
            cmd.append("--release")

        self._console.print(" ".join(cmd), Style.DIM)
        dst = self._installed_bridge_bin()
        if dry_run:
            self._console.print(f"would install bridge -> {dst}", Style.DIM)
            return True

        proc = subprocess.run(cmd, cwd=str(bridge_dir), check=False)
        if proc.returncode != 0:
            self._console.error("bridge build failed")
            return False

        built = self._built_bridge_bin(bridge_dir, release=release)
        if not built.exists():
            self._console.error(f"bridge binary missing: {built}")
            return False

        self._console.print(f"install bridge -> {dst}", Style.DIM)

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(built, dst)
        try:
            dst.chmod(0o755)
        except Exception:
            pass

        src_config = bridge_dir / "config"
        if src_config.is_dir():
            shutil.copytree(src_config, dst.parent / "config", dirs_exist_ok=True)

        self._console.success(str(dst))
        return True

    def run(self, *, args: list[str]) -> int:
        exe = self._installed_bridge_bin()
        if not exe.exists():
            # Fall back to build output.
            bridge_dir = self._bridge_dir()
            exe = self._built_bridge_bin(bridge_dir, release=True)

        if not exe.exists():
            self._console.error(f"oc-bridge not found: {exe}")
            self._console.print("hint: Run: uv run ms bridge build", Style.DIM)
            return int(ErrorCode.ENV_ERROR)

        cmd = [str(exe), *args]
        self._console.print(" ".join(cmd), Style.DIM)
        return subprocess.run(cmd, cwd=str(self._workspace.root), check=False).returncode

    def _bridge_dir(self) -> Path:
        rel = self._config.paths.bridge if self._config is not None else "open-control/bridge"
        return self._workspace.root / rel

    def _built_bridge_bin(self, bridge_dir: Path, *, release: bool) -> Path:
        profile = "release" if release else "debug"
        exe_name = self._platform.platform.exe_name("oc-bridge")
        return bridge_dir / "target" / profile / exe_name

    def _installed_bridge_bin(self) -> Path:
        exe_name = self._platform.platform.exe_name("oc-bridge")
        return self._workspace.bin_dir / "bridge" / exe_name
