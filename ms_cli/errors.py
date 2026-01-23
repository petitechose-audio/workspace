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
