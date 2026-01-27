"""Upload command - build + upload firmware for Teensy targets."""

from __future__ import annotations

import typer

from ms.cli.commands._helpers import exit_on_error
from ms.cli.context import build_context
from ms.core.app import resolve
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.services.hardware import HardwareService


def upload(
    app: str = typer.Argument(..., help="App name (e.g. core, bitwig)"),
    env: str | None = typer.Option(
        None, "--env", help="PlatformIO env (e.g. dev, release)", show_default=False
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying"),
) -> None:
    """Build and upload firmware."""
    ctx = build_context()

    match resolve(app, ctx.workspace.root):
        case Err(e):
            ctx.console.error(e.message)
            if e.available:
                ctx.console.print(f"Available: {', '.join(e.available)}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.USER_ERROR))
        case Ok(app_obj):
            pass

    hw = HardwareService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    exit_on_error(hw.upload(app_obj, env=env, dry_run=dry_run), ctx)
