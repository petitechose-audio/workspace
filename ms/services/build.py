"""Build service for native and WASM targets.

Provides build orchestration using platform-native toolchains:
- Windows: Visual Studio (MSVC) via "Visual Studio 17 2022" generator
- Linux/macOS: System compiler (GCC/Clang) via Ninja generator
- WASM: Emscripten via emcmake + Ninja
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ms.core.codebase import CodebaseError, resolve
from ms.core.config import Config
from ms.core.errors import ErrorCode
from ms.core.result import Err
from ms.core.workspace import Workspace
from ms.output.console import ConsoleProtocol, Style
from ms.platform.detection import Platform, PlatformInfo
from ms.tools.registry import ToolRegistry


@dataclass(frozen=True, slots=True)
class AppConfig:
    app_id: str
    exe_name: str


class BuildService:
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

    def build_native(self, *, codebase: str, dry_run: bool = False) -> bool:
        """Build native executable for current platform."""
        res = resolve(codebase, self._workspace.root)
        if isinstance(res, Err):
            self._print_codebase_error(res.error)
            return False

        cb = res.value
        if cb.sdl_path is None:
            self._console.error(f"SDL app not found for codebase: {codebase}")
            return False

        app_cfg = self._read_app_config(cb.sdl_path)
        if app_cfg is None:
            return False

        if not self._ensure_core_layout():
            return False

        if not self._ensure_pio_libdeps(dry_run=dry_run):
            return False

        cmake = self._tool_path("cmake")
        if cmake is None:
            return False

        sdl_src = self._core_sdl_dir()
        build_dir = self._workspace.build_dir / app_cfg.app_id / "native"
        build_dir.mkdir(parents=True, exist_ok=True)

        env = self._base_env()

        # Platform-specific CMake configuration
        if self._platform.platform == Platform.WINDOWS:
            # Windows: use Visual Studio generator (works without vcvars)
            if not self._ensure_windows_native_prereqs():
                return False

            sdl2_root = self._registry.tools_dir / "sdl2"
            configure_args = [
                str(cmake),
                "-G",
                "Visual Studio 17 2022",
                "-A",
                "x64",
                "-S",
                str(sdl_src),
                "-B",
                str(build_dir),
                f"-DAPP_PATH={cb.sdl_path}",
                f"-DBIN_OUTPUT_DIR={self._workspace.bin_dir}",
                f"-DSDL2_ROOT={sdl2_root}",
            ]
            build_args = [
                str(cmake),
                "--build",
                str(build_dir),
                "--config",
                "Release",
            ]
        else:
            # Linux/macOS: use Ninja generator with system compiler
            ninja = self._tool_path("ninja")
            if ninja is None:
                return False

            configure_args = [
                str(cmake),
                "-G",
                "Ninja",
                "-S",
                str(sdl_src),
                "-B",
                str(build_dir),
                f"-DAPP_PATH={cb.sdl_path}",
                f"-DBIN_OUTPUT_DIR={self._workspace.bin_dir}",
                "-DCMAKE_BUILD_TYPE=Release",
                f"-DCMAKE_MAKE_PROGRAM={ninja}",
            ]
            build_args = [str(ninja), "-C", str(build_dir)]

        # Configure
        self._console.print(" ".join(configure_args), Style.DIM)
        if not dry_run:
            if (
                subprocess.run(
                    configure_args, cwd=str(self._workspace.root), env=env, check=False
                ).returncode
                != 0
            ):
                self._console.error("cmake configure failed")
                return False

        # Build
        self._console.print(" ".join(build_args), Style.DIM)
        if not dry_run:
            if (
                subprocess.run(
                    build_args, cwd=str(self._workspace.root), env=env, check=False
                ).returncode
                != 0
            ):
                self._console.error("build failed")
                return False

        # Verify output
        out_dir = self._workspace.bin_dir / app_cfg.app_id / "native"
        out_exe = out_dir / self._platform.platform.exe_name(app_cfg.exe_name)
        if not dry_run and not out_exe.exists():
            self._console.error(f"native binary not found: {out_exe}")
            return False

        # Copy SDL2.dll on Windows
        if not dry_run and self._platform.platform == Platform.WINDOWS:
            import shutil

            sdl2_dll = self._registry.tools_dir / "sdl2" / "lib" / "x64" / "SDL2.dll"
            if sdl2_dll.exists():
                shutil.copy2(sdl2_dll, out_dir / "SDL2.dll")

        self._console.success(str(out_exe))
        return True

    def run_native(self, *, codebase: str) -> int:
        """Build and run native executable."""
        res = resolve(codebase, self._workspace.root)
        if isinstance(res, Err):
            self._print_codebase_error(res.error)
            return int(ErrorCode.USER_ERROR)

        cb = res.value
        if cb.sdl_path is None:
            self._console.error(f"SDL app not found for codebase: {codebase}")
            return int(ErrorCode.ENV_ERROR)

        app_cfg = self._read_app_config(cb.sdl_path)
        if app_cfg is None:
            return int(ErrorCode.ENV_ERROR)

        if not self.build_native(codebase=codebase):
            return int(ErrorCode.BUILD_ERROR)

        exe = (
            self._workspace.bin_dir
            / app_cfg.app_id
            / "native"
            / self._platform.platform.exe_name(app_cfg.exe_name)
        )
        if not exe.exists():
            self._console.error(f"native binary not found: {exe}")
            return int(ErrorCode.IO_ERROR)

        self._console.print(f"run: {exe}", Style.DIM)
        return subprocess.run([str(exe)], cwd=str(self._workspace.root), check=False).returncode

    def build_wasm(self, *, codebase: str, dry_run: bool = False) -> bool:
        """Build WebAssembly target using Emscripten."""
        res = resolve(codebase, self._workspace.root)
        if isinstance(res, Err):
            self._print_codebase_error(res.error)
            return False

        cb = res.value
        if cb.sdl_path is None:
            self._console.error(f"SDL app not found for codebase: {codebase}")
            return False

        app_cfg = self._read_app_config(cb.sdl_path)
        if app_cfg is None:
            return False

        if not self._ensure_core_layout():
            return False

        if not self._ensure_pio_libdeps(dry_run=dry_run):
            return False

        cmake = self._tool_path("cmake")
        ninja = self._tool_path("ninja")
        if cmake is None or ninja is None:
            return False

        emcmake = self._emcmake_py()
        if emcmake is None:
            return False

        sdl_src = self._core_sdl_dir()
        build_dir = self._workspace.build_dir / app_cfg.app_id / "wasm"
        build_dir.mkdir(parents=True, exist_ok=True)

        env = self._base_env()
        env["EM_CONFIG"] = str(self._registry.tools_dir / "emsdk" / ".emscripten")
        env.setdefault("EMSDK_PYTHON", sys.executable)

        configure_args = [
            sys.executable,
            str(emcmake),
            str(cmake),
            "-G",
            "Ninja",
            "-S",
            str(sdl_src),
            "-B",
            str(build_dir),
            f"-DAPP_PATH={cb.sdl_path}",
            f"-DBIN_OUTPUT_DIR={self._workspace.bin_dir}",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_MAKE_PROGRAM={ninja}",
        ]

        self._console.print(" ".join(str(x) for x in configure_args), Style.DIM)
        if not dry_run:
            if (
                subprocess.run(
                    configure_args, cwd=str(self._workspace.root), env=env, check=False
                ).returncode
                != 0
            ):
                self._console.error("emcmake/cmake configure failed")
                return False

            build_cmd = [str(ninja), "-C", str(build_dir)]
            self._console.print(" ".join(build_cmd), Style.DIM)
            if (
                subprocess.run(
                    build_cmd, cwd=str(self._workspace.root), env=env, check=False
                ).returncode
                != 0
            ):
                self._console.error("ninja build failed")
                return False

        out_html = self._workspace.bin_dir / app_cfg.app_id / "wasm" / f"{app_cfg.exe_name}.html"
        if not dry_run and not out_html.exists():
            self._console.error(f"wasm output not found: {out_html}")
            return False

        self._console.success(str(out_html))
        return True

    def serve_wasm(self, *, codebase: str, port: int = 8000) -> int:
        """Build WASM and serve via HTTP."""
        res = resolve(codebase, self._workspace.root)
        if isinstance(res, Err):
            self._print_codebase_error(res.error)
            return int(ErrorCode.USER_ERROR)

        cb = res.value
        if cb.sdl_path is None:
            self._console.error(f"SDL app not found for codebase: {codebase}")
            return int(ErrorCode.ENV_ERROR)

        app_cfg = self._read_app_config(cb.sdl_path)
        if app_cfg is None:
            return int(ErrorCode.ENV_ERROR)

        if not self.build_wasm(codebase=codebase):
            return int(ErrorCode.BUILD_ERROR)

        out_dir = self._workspace.bin_dir / app_cfg.app_id / "wasm"
        if not out_dir.exists():
            self._console.error(f"wasm output dir not found: {out_dir}")
            return int(ErrorCode.IO_ERROR)

        html = out_dir / f"{app_cfg.exe_name}.html"
        url_path = html.name if html.exists() else ""
        self._console.print(f"serve: http://localhost:{port}/{url_path}", Style.INFO)

        cmd = [sys.executable, "-m", "http.server", str(port), "-d", str(out_dir)]
        return subprocess.run(cmd, cwd=str(self._workspace.root), check=False).returncode

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _core_sdl_dir(self) -> Path:
        return self._workspace.midi_studio_dir / "core" / "sdl"

    def _ensure_core_layout(self) -> bool:
        if not (self._workspace.midi_studio_dir / "core").is_dir():
            self._console.error("midi-studio/core is missing")
            self._console.print("hint: Run: uv run ms repos sync", Style.DIM)
            return False
        if not (self._workspace.open_control_dir).is_dir():
            self._console.error("open-control is missing")
            self._console.print("hint: Run: uv run ms repos sync", Style.DIM)
            return False
        if not self._core_sdl_dir().is_dir():
            self._console.error(f"SDL build system not found: {self._core_sdl_dir()}")
            return False
        return True

    def _ensure_pio_libdeps(self, *, dry_run: bool) -> bool:
        """Ensure PlatformIO libdeps are installed (provides LVGL)."""
        core_dir = self._workspace.midi_studio_dir / "core"
        libdeps = core_dir / ".pio" / "libdeps"
        if libdeps.is_dir():
            return True

        pio = self._pio_cmd()
        if pio is None:
            return False

        cmd = [str(pio), "pkg", "install"]
        self._console.print(" ".join(cmd), Style.DIM)
        if dry_run:
            return True

        proc = subprocess.run(cmd, cwd=str(core_dir), env=self._base_env(), check=False)
        if proc.returncode != 0:
            self._console.error("pio pkg install failed")
            return False
        return True

    def _ensure_windows_native_prereqs(self) -> bool:
        """Check Windows native build prerequisites (MSVC, SDL2)."""
        # Check SDL2-VC is installed
        sdl2_lib = self._registry.tools_dir / "sdl2" / "lib" / "x64" / "SDL2.lib"
        if not sdl2_lib.exists():
            self._console.error("SDL2 (VC) not found")
            self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
            return False

        # Check for Visual Studio (via vswhere)
        vswhere = self._find_vswhere()
        if vswhere is None:
            self._console.error("Visual Studio Build Tools not found")
            self._console.print(
                "hint: Install from https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022",
                Style.DIM,
            )
            return False

        # Verify C++ workload is installed
        # Note: -products * is required to include Build Tools (not just full VS)
        try:
            result = subprocess.run(
                [
                    str(vswhere),
                    "-latest",
                    "-products",
                    "*",
                    "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                    "-property",
                    "installationPath",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0 or not result.stdout.strip():
                self._console.error("Visual Studio C++ workload not found")
                self._console.print(
                    "hint: Install 'Desktop development with C++' workload",
                    Style.DIM,
                )
                return False
        except Exception:
            self._console.error("Failed to query Visual Studio installation")
            return False

        return True

    def _find_vswhere(self) -> Path | None:
        """Find vswhere.exe (Visual Studio locator)."""
        # Standard location
        program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        vswhere = Path(program_files) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        if vswhere.exists():
            return vswhere

        # Try PATH
        found = shutil.which("vswhere")
        if found:
            return Path(found)

        return None

    def _base_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.update(self._registry.get_env_vars())
        env.update(self._platformio_env_vars())
        return env

    def _platformio_env_vars(self) -> dict[str, str]:
        return {
            "PLATFORMIO_CORE_DIR": str(self._workspace.state_dir / "platformio"),
            "PLATFORMIO_CACHE_DIR": str(self._workspace.state_dir / "platformio-cache"),
            "PLATFORMIO_BUILD_CACHE_DIR": str(self._workspace.state_dir / "platformio-build-cache"),
        }

    def _tool_path(self, tool_id: str) -> Path | None:
        p = self._registry.get_bin_path(tool_id)
        if p is not None and p.exists():
            return p
        found = shutil.which(tool_id)
        if found:
            return Path(found)
        self._console.error(f"{tool_id}: missing")
        self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
        return None

    def _pio_cmd(self) -> Path | None:
        name = "pio.cmd" if self._platform.platform == Platform.WINDOWS else "pio"
        wrapper = self._workspace.tools_bin_dir / name
        if wrapper.exists():
            return wrapper

        pio = self._registry.get_bin_path("platformio")
        if pio is not None and pio.exists():
            return pio

        self._console.error("platformio: missing")
        self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
        return None

    def _emcmake_py(self) -> Path | None:
        emcmake = self._registry.tools_dir / "emsdk" / "upstream" / "emscripten" / "emcmake.py"
        if emcmake.exists():
            return emcmake
        self._console.error(f"emcmake.py not found: {emcmake}")
        self._console.print("hint: Run: uv run ms tools sync", Style.DIM)
        return None

    def _read_app_config(self, app_path: Path) -> AppConfig | None:
        app_cmake = app_path / "app.cmake"
        if not app_cmake.exists():
            self._console.error(f"app config not found: {app_cmake}")
            return None

        content = app_cmake.read_text(encoding="utf-8")
        app_id = _extract_cmake_var(content, "APP_ID")
        exe_name = _extract_cmake_var(content, "APP_EXE_NAME")
        if not app_id or not exe_name:
            self._console.error(f"invalid app config: {app_cmake}")
            return None
        return AppConfig(app_id=app_id, exe_name=exe_name)

    def _print_codebase_error(self, err: CodebaseError) -> None:
        msg = err.message
        if err.available:
            msg += f"\nAvailable: {', '.join(err.available)}"
        self._console.error(msg)


_CMAKE_SET_RE = re.compile(r"^\s*set\(\s*(?P<name>[A-Z0-9_]+)\s+\"(?P<value>[^\"]+)\"\s*\)\s*$")


def _extract_cmake_var(content: str, name: str) -> str | None:
    for line in content.splitlines():
        m = _CMAKE_SET_RE.match(line)
        if not m:
            continue
        if m.group("name") == name:
            return m.group("value")
    return None
