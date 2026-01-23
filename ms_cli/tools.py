"""
Cross-platform tool resolution.

Finds actual executables (not bash wrappers) for build tools.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .platform import detect_platform, is_windows
from .errors import get_install_hint


class ToolNotFoundError(Exception):
    """Raised when a required tool cannot be found."""

    def __init__(self, tool: str):
        self.tool = tool
        hint = get_install_hint(tool)
        msg = f"{tool} not found"
        if hint:
            msg += f"\n\nInstall with:\n  {hint}"
        super().__init__(msg)


class ToolResolver:
    """
    Resolves actual tool executables across platforms.

    Strategy:
    1. Try workspace-bundled tools first (tools/<name>/<exe>)
    2. Fall back to system PATH
    3. Never use bash wrappers (tools/bin/<name>)
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.tools_dir = workspace / "tools"
        self.platform = detect_platform()
        self._cache: dict[str, Path] = {}

    def cmake(self) -> Path:
        """Find cmake executable."""
        return self._resolve(
            "cmake",
            [
                self.tools_dir / "cmake" / "bin" / self._exe("cmake"),
            ],
        )

    def ninja(self) -> Path:
        """Find ninja executable."""
        return self._resolve(
            "ninja",
            [
                self.tools_dir / "ninja" / self._exe("ninja"),
            ],
        )

    def pio(self) -> Path:
        """Find PlatformIO CLI executable."""
        home = Path.home()
        return self._resolve(
            "pio",
            [
                home / ".platformio" / "penv" / "Scripts" / "pio.exe",
                home / ".platformio" / "penv" / "bin" / "pio",
            ],
        )

    def cargo(self) -> Path:
        """Find cargo (Rust) executable."""
        return self._resolve("cargo", [])

    def mvn(self) -> Path:
        """Find Maven executable."""
        return self._resolve(
            "mvn",
            [
                self.tools_dir / "maven" / "bin" / "mvn.cmd",
                self.tools_dir / "maven" / "bin" / "mvn",
            ],
            allow_cmd=True,
        )

    def java(self) -> Path:
        """Find Java executable."""
        return self._resolve(
            "java",
            [
                self.tools_dir / "jdk" / "bin" / self._exe("java"),
            ],
        )

    def zig(self) -> Path:
        """Find Zig executable."""
        return self._resolve(
            "zig",
            [
                self.tools_dir / "zig" / self._exe("zig"),
            ],
        )

    def zig_cc(self) -> Path:
        """Find zig-cc wrapper for CMake (handles 'zig cc' invocation)."""
        if is_windows():
            return self.tools_dir / "bin" / "zig-cc.cmd"
        return self.tools_dir / "bin" / "zig-cc"

    def zig_cxx(self) -> Path:
        """Find zig-cxx wrapper for CMake (handles 'zig c++' invocation)."""
        if is_windows():
            return self.tools_dir / "bin" / "zig-cxx.cmd"
        return self.tools_dir / "bin" / "zig-cxx"

    def bun(self) -> Path:
        """Find Bun executable."""
        return self._resolve(
            "bun",
            [
                self.tools_dir / "bun" / self._exe("bun"),
            ],
        )

    def emcmake(self) -> Path:
        """Find emcmake.py (Emscripten CMake wrapper)."""
        script = self.tools_dir / "emsdk" / "upstream" / "emscripten" / "emcmake.py"
        if script.exists():
            return script
        raise ToolNotFoundError("emcmake")

    def emcc(self) -> Path:
        """Find emcc.py (Emscripten compiler)."""
        script = self.tools_dir / "emsdk" / "upstream" / "emscripten" / "emcc.py"
        if script.exists():
            return script
        raise ToolNotFoundError("emcc")

    def python(self) -> Path:
        """Find Python executable for emscripten scripts."""
        # Try workspace venv first
        venv_python = (
            self.workspace
            / ".venv"
            / ("Scripts" if is_windows() else "bin")
            / self._exe("python")
        )
        if venv_python.exists():
            return venv_python

        # Fall back to bundled python
        for subdir in self.tools_dir.glob("python/cpython-*"):
            py = subdir / self._exe("python")
            if py.exists():
                return py

        # Fall back to system
        return self._resolve("python", [])

    def oc_build(self) -> Optional[Path]:
        """Find oc-build script (optional)."""
        script = self.workspace / "open-control" / "cli-tools" / "bin" / "oc-build"
        return script if script.exists() else None

    def oc_upload(self) -> Optional[Path]:
        """Find oc-upload script (optional)."""
        script = self.workspace / "open-control" / "cli-tools" / "bin" / "oc-upload"
        return script if script.exists() else None

    def oc_monitor(self) -> Optional[Path]:
        """Find oc-monitor script (optional)."""
        script = self.workspace / "open-control" / "cli-tools" / "bin" / "oc-monitor"
        return script if script.exists() else None

    def bash(self) -> Optional[Path]:
        """Find bash executable (Git Bash on Windows)."""
        if not is_windows():
            found = shutil.which("bash")
            return Path(found) if found else None

        # Windows: prefer Git Bash
        path_env = os.environ.get("PATH", "")
        for entry in path_env.split(os.pathsep):
            entry = entry.strip('"')
            if not entry:
                continue
            entry_lower = entry.lower()
            if "git" in entry_lower and (
                "\\usr\\bin" in entry_lower or "/usr/bin" in entry_lower
            ):
                candidate = Path(entry) / "bash.exe"
                if candidate.exists():
                    return candidate

        # Try msys64
        for entry in path_env.split(os.pathsep):
            entry = entry.strip('"')
            if not entry:
                continue
            entry_lower = entry.lower()
            if "msys64" in entry_lower and (
                "\\usr\\bin" in entry_lower or "/usr/bin" in entry_lower
            ):
                candidate = Path(entry) / "bash.exe"
                if candidate.exists():
                    return candidate

        return None

    def sdl2_dir(self) -> Optional[Path]:
        """Find SDL2 directory (Windows only, bundled)."""
        if not is_windows():
            return None
        sdl2 = self.tools_dir / "windows" / "SDL2"
        return sdl2 if sdl2.exists() else None

    def _resolve(self, name: str, bundled: list[Path], allow_cmd: bool = False) -> Path:
        """Resolve tool by trying bundled paths, then system PATH."""
        if name in self._cache:
            return self._cache[name]

        for path in bundled:
            if path.exists():
                self._cache[name] = path
                return path

        found = shutil.which(name)
        if found:
            self._cache[name] = Path(found)
            return Path(found)

        if allow_cmd and is_windows():
            found = shutil.which(f"{name}.cmd")
            if found:
                self._cache[name] = Path(found)
                return Path(found)

        raise ToolNotFoundError(name)

    def _exe(self, name: str) -> str:
        """Add .exe suffix on Windows."""
        return f"{name}.exe" if is_windows() else name


def run_tool(
    tool: Path,
    args: list[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    capture: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a tool with proper Windows handling.

    Handles .cmd/.bat files via cmd.exe /c.
    """
    cmd = [str(tool), *args]

    if is_windows():
        ext = tool.suffix.lower()
        if ext in {".cmd", ".bat"}:
            cmd = ["cmd", "/c", str(tool), *args]

    run_env = None
    if env:
        run_env = os.environ.copy()
        run_env.update(env)

    kwargs: dict = {
        "cwd": str(cwd) if cwd else None,
        "env": run_env,
    }

    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True

    return subprocess.run(cmd, **kwargs)


def run_bash_script(
    script: Path,
    args: list[str],
    *,
    bash: Path,
    cwd: Optional[Path] = None,
) -> int:
    """Run a bash script (for oc-* tools)."""
    return subprocess.call(
        [str(bash), str(script), *args],
        cwd=str(cwd) if cwd else None,
    )
