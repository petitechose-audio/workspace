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

    - "core" -> midi-studio/core
    - "bitwig" -> midi-studio/plugin-bitwig
    """
    midi_studio = workspace / "midi-studio"

    if name == "core":
        path = midi_studio / "core"
    else:
        path = midi_studio / f"plugin-{name}"

    if not path.is_dir():
        available = list_codebases(workspace)
        raise CodebaseNotFoundError(
            f"Unknown codebase: {name}\nAvailable: {', '.join(available)}"
        )

    # SDL sources (check for app.cmake, not CMakeLists.txt)
    sdl_path = None
    if (path / "sdl" / "app.cmake").exists():
        sdl_path = path / "sdl"
    elif (midi_studio / "core" / "sdl" / "app.cmake").exists():
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
