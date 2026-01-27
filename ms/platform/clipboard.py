"""Cross-platform clipboard support."""

from __future__ import annotations

import subprocess
import sys


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard.

    Returns True on success, False on failure.
    Supports Windows, macOS, and Linux (with xclip).
    """
    if sys.platform == "win32":
        return _copy_windows(text)
    elif sys.platform == "darwin":
        return _copy_macos(text)
    else:
        return _copy_linux(text)


def _copy_windows(text: str) -> bool:
    """Copy to clipboard on Windows using clip.exe."""
    try:
        proc = subprocess.run(
            ["clip"],
            input=text.encode("utf-8"),
            check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def _copy_macos(text: str) -> bool:
    """Copy to clipboard on macOS using pbcopy."""
    try:
        proc = subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False


def _copy_linux(text: str) -> bool:
    """Copy to clipboard on Linux using xclip."""
    try:
        proc = subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode("utf-8"),
            check=False,
        )
        return proc.returncode == 0
    except OSError:
        return False
