from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.services.setup import SetupService


def setup(
    mode: str = typer.Option("dev", "--mode", help="Setup mode (dev only)"),
    skip_repos: bool = typer.Option(False, "--skip-repos", help="Skip repository sync"),
    skip_tools: bool = typer.Option(False, "--skip-tools", help="Skip toolchain sync"),
    skip_python: bool = typer.Option(False, "--skip-python", help="Skip Python deps sync"),
    skip_check: bool = typer.Option(False, "--skip-check", help="Skip final check"),
    skip_prereqs: bool = typer.Option(
        False,
        "--skip-prereqs",
        "--skip-system-deps",
        help="Skip prerequisites check/install",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm (do not prompt)"),
) -> None:
    """Setup dev workspace.

    Checks and installs prerequisites, syncs repositories,
    installs toolchains, and validates the environment.

    Installs prompt for confirmation unless --yes is passed.
    """
    ctx = build_context()
    service = SetupService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
        confirm=lambda msg: typer.confirm(msg, default=False),
    )

    result = service.setup_dev(
        mode=mode,
        skip_repos=skip_repos,
        skip_tools=skip_tools,
        skip_python=skip_python,
        skip_check=skip_check,
        skip_prereqs=skip_prereqs,
        dry_run=dry_run,
        assume_yes=yes,
    )
    match result:
        case Ok(_):
            ctx.console.newline()
            ctx.console.success("Setup complete")
        case Err(e):
            ctx.console.error(f"setup failed: {e.message}")
            if e.hint:
                ctx.console.print(e.hint)
            raise typer.Exit(code=int(ErrorCode.ENV_ERROR))
