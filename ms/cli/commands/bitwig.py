from __future__ import annotations

from pathlib import Path

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.services.bitwig import BitwigService


bitwig_app = typer.Typer(no_args_is_help=True)


@bitwig_app.command("build")
def build(
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
) -> None:
    """Build the Bitwig extension (.bwextension) into host/target/."""
    ctx = build_context()
    service = BitwigService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    ok = service.build(dry_run=dry_run)
    if not ok:
        raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))


@bitwig_app.command("deploy")
def deploy(
    dir: Path | None = typer.Option(
        None,
        "--dir",
        help="Bitwig Extensions directory (overrides config + defaults).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
) -> None:
    """Build and deploy the Bitwig extension into the Extensions directory."""
    ctx = build_context()
    service = BitwigService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    ok = service.deploy(extensions_dir=dir, dry_run=dry_run)
    if not ok:
        raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))
