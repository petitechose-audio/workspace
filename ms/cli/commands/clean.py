"""Clean command - remove build artifacts and caches."""

from __future__ import annotations

import shutil
from pathlib import Path

import typer
from rich.console import Console

from ms.cli.context import build_context

_console = Console()


def clean(
    all_: bool = typer.Option(False, "--all", help="Include tools and caches"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Execute (default is dry-run)"),
) -> None:
    """Clean build artifacts. Dry-run by default, use -y to execute."""
    ctx = build_context()
    ws = ctx.workspace

    # Collect directories
    dirs: list[Path] = [
        ws.build_dir,
        ws.platformio_dir,
        ws.state_dir / "platformio-cache",
        ws.state_dir / "platformio-build-cache",
        ws.midi_studio_dir / "core" / ".pio",
        ws.midi_studio_dir / "plugin-bitwig" / ".pio",
    ]

    if all_:
        dirs.extend([ws.tools_dir, ws.cache_dir])

    # Filter existing
    existing = [d for d in dirs if d.exists()]

    if not existing:
        _console.print("[dim]Nothing to clean[/dim]")
        return

    # Header
    if yes:
        _console.print("\n[bold red]EXECUTE[/bold red]\n")
    else:
        _console.print("\n[yellow]DRY-RUN[/yellow]\n")

    # List directories
    for d in existing:
        _console.print(f"  {d}", style="dim")

    # Footer
    if not yes:
        _console.print("\n[dim]Use -y to execute[/dim]")
        return

    # Execute
    for d in existing:
        shutil.rmtree(d)

    _console.print(f"\n[green]Removed {len(existing)} directories[/green]")
