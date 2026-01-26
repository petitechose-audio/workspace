from __future__ import annotations

import typer

from ms.cli.commands._helpers import exit_on_error
from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.services.prereqs import PrereqsService


def prereqs(
    install: bool = typer.Option(False, "--install", help="Install safe prerequisites"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be done"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm (do not prompt)"),
) -> None:
    """Check prerequisites required for dev setup."""
    ctx = build_context()

    result = PrereqsService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
        confirm=lambda msg: typer.confirm(msg, default=False),
    ).ensure(
        require_git=True,
        require_gh=True,
        require_gh_auth=True,
        require_uv=True,
        install=install,
        dry_run=dry_run,
        assume_yes=yes,
        fail_if_missing=True,
    )

    exit_on_error(result, ctx, error_code=ErrorCode.ENV_ERROR)
