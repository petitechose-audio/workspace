from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.services.bridge import BridgeService


bridge_app = typer.Typer(no_args_is_help=True)


@bridge_app.command("build")
def build(
    release: bool = typer.Option(True, "--release/--debug", help="Build release (default)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
) -> None:
    """Build and install oc-bridge into bin/bridge/."""
    ctx = build_context()
    service = BridgeService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    ok = service.build(release=release, dry_run=dry_run)
    if not ok:
        raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))


@bridge_app.command(
    "run",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
def run(ctx: typer.Context) -> None:
    """Run oc-bridge (TUI by default)."""
    cli = build_context()
    service = BridgeService(
        workspace=cli.workspace,
        platform=cli.platform,
        config=cli.config,
        console=cli.console,
    )
    code = service.run(args=list(ctx.args))
    raise typer.Exit(code=code)
