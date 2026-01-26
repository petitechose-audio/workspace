from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.services.setup import SetupService


def setup(
    mode: str = typer.Option("dev", "--mode", help="Setup mode (dev only)"),
    skip_repos: bool = typer.Option(False, "--skip-repos"),
    skip_tools: bool = typer.Option(False, "--skip-tools"),
    skip_python: bool = typer.Option(False, "--skip-python"),
    skip_check: bool = typer.Option(False, "--skip-check"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Setup dev workspace."""
    ctx = build_context()
    service = SetupService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    result = service.setup_dev(
        mode=mode,
        skip_repos=skip_repos,
        skip_tools=skip_tools,
        skip_python=skip_python,
        skip_check=skip_check,
        dry_run=dry_run,
    )
    match result:
        case Ok(_):
            pass
        case Err(e):
            ctx.console.error(f"setup failed: {e.message}")
            if e.hint:
                ctx.console.print(e.hint)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
