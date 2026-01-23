# Module Specifications

**Parent**: [README.md](./README.md)

This document contains the complete code specifications for each new module.

---

## 1. `ms_cli/platform.py`

```python
"""
Platform detection utilities.

Simple, stateless functions for cross-platform compatibility.
"""
from __future__ import annotations

import platform as _platform
from typing import Literal

Platform = Literal["linux", "macos", "windows", "unknown"]


def detect_platform() -> Platform:
    """
    Detect current operating system.
    
    Returns:
        "linux", "macos", "windows", or "unknown"
    """
    system = _platform.system().lower()
    if system.startswith("linux"):
        return "linux"
    if system.startswith("darwin"):
        return "macos"
    if system.startswith("windows") or system.startswith("cygwin") or system.startswith("msys"):
        return "windows"
    return "unknown"


def is_windows() -> bool:
    """Check if running on Windows."""
    return detect_platform() == "windows"


def is_linux() -> bool:
    """Check if running on Linux."""
    return detect_platform() == "linux"


def is_macos() -> bool:
    """Check if running on macOS."""
    return detect_platform() == "macos"


def detect_linux_distro() -> str:
    """
    Detect Linux distribution family.
    
    Returns:
        "fedora", "debian", "arch", "suse", or "unknown"
    """
    if not is_linux():
        return "unknown"
    
    try:
        with open("/etc/os-release") as f:
            content = f.read().lower()
            if "fedora" in content or "rhel" in content or "centos" in content:
                return "fedora"
            if "ubuntu" in content or "debian" in content or "mint" in content:
                return "debian"
            if "arch" in content or "manjaro" in content:
                return "arch"
            if "opensuse" in content or "suse" in content:
                return "suse"
    except FileNotFoundError:
        pass
    
    return "unknown"
```

---

## 2. `ms_cli/errors.py`

```python
"""
Error messages with platform-specific install hints.

Provides helpful, actionable error messages for common issues.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .platform import detect_platform, detect_linux_distro


@dataclass
class InstallHint:
    """Platform-specific installation hint."""
    fedora: str
    debian: str
    arch: str
    macos: str
    windows: str


INSTALL_HINTS: dict[str, InstallHint] = {
    "cmake": InstallHint(
        fedora="sudo dnf install cmake",
        debian="sudo apt install cmake",
        arch="sudo pacman -S cmake",
        macos="brew install cmake",
        windows="Bundled in tools/cmake (run setup.sh)",
    ),
    "ninja": InstallHint(
        fedora="sudo dnf install ninja-build",
        debian="sudo apt install ninja-build",
        arch="sudo pacman -S ninja",
        macos="brew install ninja",
        windows="Bundled in tools/ninja (run setup.sh)",
    ),
    "g++": InstallHint(
        fedora="sudo dnf install gcc-c++",
        debian="sudo apt install g++",
        arch="sudo pacman -S gcc",
        macos="xcode-select --install",
        windows="Install MinGW-w64: https://www.mingw-w64.org/",
    ),
    "cargo": InstallHint(
        fedora="curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        debian="curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        arch="sudo pacman -S rust",
        macos="curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh",
        windows="Download from https://rustup.rs",
    ),
    "pio": InstallHint(
        fedora="Run setup.sh to install PlatformIO",
        debian="Run setup.sh to install PlatformIO",
        arch="Run setup.sh to install PlatformIO",
        macos="Run setup.sh to install PlatformIO",
        windows="Run setup.sh to install PlatformIO",
    ),
    "sdl2": InstallHint(
        fedora="sudo dnf install SDL2-devel",
        debian="sudo apt install libsdl2-dev",
        arch="sudo pacman -S sdl2",
        macos="brew install sdl2",
        windows="Bundled in tools/windows/SDL2 (run setup.sh)",
    ),
    "alsa": InstallHint(
        fedora="sudo dnf install alsa-lib-devel",
        debian="sudo apt install libasound2-dev",
        arch="sudo pacman -S alsa-lib",
        macos="N/A (uses CoreMIDI)",
        windows="N/A (uses WinMM)",
    ),
    "mvn": InstallHint(
        fedora="sudo dnf install maven",
        debian="sudo apt install maven",
        arch="sudo pacman -S maven",
        macos="brew install maven",
        windows="Bundled in tools/maven (run setup.sh)",
    ),
    "git": InstallHint(
        fedora="sudo dnf install git",
        debian="sudo apt install git",
        arch="sudo pacman -S git",
        macos="xcode-select --install",
        windows="Install Git for Windows: https://git-scm.com/",
    ),
}


def get_install_hint(tool: str) -> Optional[str]:
    """
    Get platform-specific install command for a tool.
    
    Returns:
        Install command string, or None if unknown
    """
    hint = INSTALL_HINTS.get(tool)
    if not hint:
        return None
    
    platform = detect_platform()
    
    if platform == "windows":
        return hint.windows
    elif platform == "macos":
        return hint.macos
    elif platform == "linux":
        distro = detect_linux_distro()
        if distro == "fedora":
            return hint.fedora
        elif distro == "debian":
            return hint.debian
        elif distro == "arch":
            return hint.arch
        else:
            return f"{hint.debian}  # (adjust for your distro)"
    
    return None


def format_missing_tools(tools: list[str]) -> str:
    """
    Format error message for missing tools with install suggestions.
    
    Example output:
        Missing dependencies:
          - cmake
          - ninja
        
        Install with:
          sudo apt install cmake ninja-build
    """
    if not tools:
        return ""
    
    lines = ["Missing dependencies:"]
    for tool in tools:
        lines.append(f"  - {tool}")
    
    lines.append("")
    lines.append("Install with:")
    
    for tool in tools:
        hint = get_install_hint(tool)
        if hint:
            lines.append(f"  {hint}")
    
    return "\n".join(lines)
```

---

## 3. `ms_cli/tools.py`

```python
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
        return self._resolve("cmake", [
            self.tools_dir / "cmake" / "bin" / self._exe("cmake"),
        ])
    
    def ninja(self) -> Path:
        """Find ninja executable."""
        return self._resolve("ninja", [
            self.tools_dir / "ninja" / self._exe("ninja"),
        ])
    
    def pio(self) -> Path:
        """Find PlatformIO CLI executable."""
        home = Path.home()
        return self._resolve("pio", [
            home / ".platformio" / "penv" / "Scripts" / "pio.exe",
            home / ".platformio" / "penv" / "bin" / "pio",
        ])
    
    def cargo(self) -> Path:
        """Find cargo (Rust) executable."""
        return self._resolve("cargo", [])
    
    def mvn(self) -> Path:
        """Find Maven executable."""
        return self._resolve("mvn", [
            self.tools_dir / "maven" / "bin" / "mvn.cmd",
            self.tools_dir / "maven" / "bin" / "mvn",
        ], allow_cmd=True)
    
    def emcmake(self) -> Path:
        """Find emcmake.py (Emscripten CMake wrapper)."""
        script = self.tools_dir / "emsdk" / "upstream" / "emscripten" / "emcmake.py"
        if script.exists():
            return script
        raise ToolNotFoundError("emcmake")
    
    def python(self) -> Path:
        """Find Python executable for emscripten scripts."""
        # Try workspace venv first
        venv_python = self.workspace / ".venv" / ("Scripts" if is_windows() else "bin") / self._exe("python")
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
            entry_lower = entry.lower()
            if "git" in entry_lower and "usr\\bin" in entry_lower:
                candidate = Path(entry) / "bash.exe"
                if candidate.exists():
                    return candidate
        
        return None
    
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
    
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=run_env,
    )


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
```

---

## 4. `ms_cli/codebase.py`

```python
"""
Codebase resolution and management.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class CodebaseNotFoundError(Exception):
    """Raised when a codebase cannot be found."""
    pass


@dataclass
class Codebase:
    """Resolved codebase information."""
    name: str
    path: Path
    sdl_path: Optional[Path]
    has_teensy: bool
    has_sdl: bool


def resolve_codebase(name: str, workspace: Path) -> Codebase:
    """
    Resolve codebase name to paths.
    
    - "core" → midi-studio/core
    - "bitwig" → midi-studio/plugin-bitwig
    """
    midi_studio = workspace / "midi-studio"
    
    if name == "core":
        path = midi_studio / "core"
    else:
        path = midi_studio / f"plugin-{name}"
    
    if not path.is_dir():
        available = list_codebases(workspace)
        raise CodebaseNotFoundError(
            f"Unknown codebase: {name}\n"
            f"Available: {', '.join(available)}"
        )
    
    # SDL sources
    sdl_path = None
    if (path / "sdl" / "CMakeLists.txt").exists():
        sdl_path = path / "sdl"
    elif (midi_studio / "core" / "sdl" / "CMakeLists.txt").exists():
        sdl_path = midi_studio / "core" / "sdl"
    
    return Codebase(
        name=name,
        path=path,
        sdl_path=sdl_path,
        has_teensy=(path / "platformio.ini").exists(),
        has_sdl=sdl_path is not None,
    )


def list_codebases(workspace: Path) -> list[str]:
    """List all available codebases."""
    midi_studio = workspace / "midi-studio"
    codebases = []
    
    if (midi_studio / "core").is_dir():
        codebases.append("core")
    
    for child in sorted(midi_studio.iterdir()):
        if child.is_dir() and child.name.startswith("plugin-"):
            codebases.append(child.name.removeprefix("plugin-"))
    
    return codebases
```

---

## 5. `ms_cli/bridge.py`

```python
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
                "--controller", config.transport,
                "--controller-port", str(config.controller_port),
                "--udp-port", str(config.host_port),
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
    
    def _find_executable(self) -> Optional[Path]:
        """Find bridge executable."""
        name = "oc-bridge.exe" if is_windows() else "oc-bridge"
        
        exe = self.workspace / "bin" / "bridge" / name
        if exe.exists():
            return exe
        
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
        match = re.search(r'\.port\s*=\s*(\d+)', content)
    else:
        match = re.search(r'localhost:(\d+)', content)
    
    return int(match.group(1)) if match else None


def get_bridge_config(codebase_path: Path, target: Literal["native", "wasm"]) -> Optional[BridgeConfig]:
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
```

---

## 6. Build Modules

See separate files in `ms_cli/build/`:
- `native.py` - CMake + Ninja builds
- `wasm.py` - Emscripten builds
- `teensy.py` - PlatformIO builds

These follow the same patterns as above, using `ToolResolver` and `Codebase`.
