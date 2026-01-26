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
        process = subprocess.Popen(
            ["clip"],
            stdin=subprocess.PIPE,
            shell=True,
        )
        process.communicate(text.encode("utf-8"))
        return process.returncode == 0
    except Exception:
        return False


def _copy_macos(text: str) -> bool:
    """Copy to clipboard on macOS using pbcopy."""
    try:
        process = subprocess.Popen(
            ["pbcopy"],
            stdin=subprocess.PIPE,
        )
        process.communicate(text.encode("utf-8"))
        return process.returncode == 0
    except Exception:
        return False


def _copy_linux(text: str) -> bool:
    """Copy to clipboard on Linux using xclip."""
    try:
        process = subprocess.Popen(
            ["xclip", "-selection", "clipboard"],
            stdin=subprocess.PIPE,
        )
        process.communicate(text.encode("utf-8"))
        return process.returncode == 0
    except Exception:
        return False
