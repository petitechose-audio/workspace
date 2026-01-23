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
    if (
        system.startswith("windows")
        or system.startswith("cygwin")
        or system.startswith("msys")
    ):
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
