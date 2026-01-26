from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.services.build import BuildService


def build(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    target: str = typer.Argument(..., help="Target: native|wasm"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
) -> None:
    """Build native or WASM simulator."""
    ctx = build_context()
    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    if target == "native":
        ok = service.build_native(codebase=codebase, dry_run=dry_run)
    elif target == "wasm":
        ok = service.build_wasm(codebase=codebase, dry_run=dry_run)
    else:
        raise typer.Exit(code=int(ErrorCode.USER_ERROR))

    if not ok:
        raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))


def run(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
) -> None:
    """Build and run native simulator."""
    ctx = build_context()
    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    code = service.run_native(codebase=codebase)
    raise typer.Exit(code=code)


def web(
    codebase: str = typer.Argument(..., help="Codebase: core, bitwig, ..."),
    port: int = typer.Option(8000, "--port", "-p", help="HTTP server port"),
) -> None:
    """Build and serve WASM simulator."""
    ctx = build_context()
    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    code = service.serve_wasm(codebase=codebase, port=port)
    raise typer.Exit(code=code)
