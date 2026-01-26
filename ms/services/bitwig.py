from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from ms.core.config import Config
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import Platform, PlatformInfo
from ms.platform.paths import home
from ms.tools.registry import ToolRegistry


class BitwigService:
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

        tools_dir = workspace.root / (config.paths.tools if config else "tools")
        self._registry = ToolRegistry(
            tools_dir=tools_dir,
            platform=platform.platform,
            arch=platform.arch,
        )

    def build(self, *, dry_run: bool = False) -> bool:
        host_dir = self._host_dir()
        if not (host_dir / "pom.xml").exists():
            self._console.error(f"bitwig host missing: {host_dir}")
            self._console.print("hint: Run: uv run ms repos sync", Style.DIM)
            return False

        mvn = self._mvn_path()
        if mvn is None:
            self._console.error("maven: missing")
            self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
            return False

        env = self._build_env()
        cmd = [
            str(mvn),
            "package",
            "-Pmanual",
            "-Dmaven.compiler.release=21",
        ]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            return True

        proc = subprocess.run(cmd, cwd=str(host_dir), env=env, check=False)
        if proc.returncode != 0:
            self._console.error("maven build failed")
            return False

        built = host_dir / "target" / "midi_studio.bwextension"
        if not built.exists():
            self._console.error(f"extension not found: {built}")
            return False

        self._copy_to_bin(built)
        self._console.success(str(built))
        return True

    def deploy(self, *, extensions_dir: Path | None = None, dry_run: bool = False) -> bool:
        host_dir = self._host_dir()
        if not (host_dir / "pom.xml").exists():
            self._console.error(f"bitwig host missing: {host_dir}")
            self._console.print("hint: Run: uv run ms repos sync", Style.DIM)
            return False

        mvn = self._mvn_path()
        if mvn is None:
            self._console.error("maven: missing")
            self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
            return False

        install_dir = extensions_dir or self._resolve_extensions_dir()
        if install_dir is None:
            self._console.error("bitwig extensions dir not configured")
            return False

        self._console.print(f"extensions dir: {install_dir}", Style.DIM)
        if not dry_run:
            install_dir.mkdir(parents=True, exist_ok=True)

        env = self._build_env()
        cmd = [
            str(mvn),
            "package",
            "-Dmaven.compiler.release=21",
            f"-Dbitwig.extensions.dir={install_dir}",
        ]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            return True

        proc = subprocess.run(cmd, cwd=str(host_dir), env=env, check=False)
        if proc.returncode != 0:
            self._console.error("maven build failed")
            return False

        deployed = install_dir / "midi_studio.bwextension"
        if not deployed.exists():
            # Fallback: find any .bwextension file.
            matches = list(install_dir.glob("*.bwextension"))
            deployed = max(matches, key=lambda p: p.stat().st_mtime) if matches else deployed

        if not deployed.exists():
            self._console.error(f"extension not found: {deployed}")
            return False

        self._copy_to_bin(deployed)
        self._console.success(str(deployed))
        return True

    def _host_dir(self) -> Path:
        rel = (
            self._config.paths.extension
            if self._config is not None
            else "midi-studio/plugin-bitwig/host"
        )
        return self._workspace.root / rel

    def _resolve_extensions_dir(self) -> Path | None:
        platform = self._platform.platform
        platform_key = str(platform)
        configured = self._config.bitwig.as_dict().get(platform_key) if self._config else None

        if configured:
            p = _expand_user_vars(configured)
            if not p.is_absolute():
                p = self._workspace.root / p
            return p

        h = home()
        match platform:
            case Platform.LINUX:
                return _first_existing_or_default(
                    [h / "Bitwig Studio" / "Extensions", h / ".BitwigStudio" / "Extensions"],
                )
            case Platform.MACOS:
                return h / "Documents" / "Bitwig Studio" / "Extensions"
            case Platform.WINDOWS:
                return h / "Documents" / "Bitwig Studio" / "Extensions"
            case _:
                return None

    def _mvn_path(self) -> Path | None:
        mvn = self._registry.get_bin_path("maven")
        if mvn is not None and mvn.exists():
            return mvn
        found = shutil.which("mvn")
        if found:
            return Path(found)
        return None

    def _build_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._registry.get_env_vars())
        return env

    def _copy_to_bin(self, src: Path) -> None:
        dst_dir = self._workspace.bin_dir / "bitwig"
        dst_dir.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, dst_dir / src.name)
        except Exception:
            pass


def _expand_user_vars(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def _first_existing_or_default(candidates: list[Path]) -> Path:
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]
