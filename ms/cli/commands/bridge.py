"""Bridge command - build and run oc-bridge."""

from __future__ import annotations

import typer

from ms.cli.context import build_context
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.services.bridge import BridgeService


def bridge(
    build: bool = typer.Option(False, "--build", help="Force rebuild"),
) -> None:
    """Run bridge (builds if needed)."""
    ctx = build_context()
    service = BridgeService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    needs_build = build or not service.is_installed()

    if needs_build:
        result = service.build()
        match result:
            case Err(e):
                ctx.console.error(e.message)
                if e.hint:
                    ctx.console.print(f"hint: {e.hint}", Style.DIM)
                raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))
            case Ok(_):
                pass

    code = service.run(args=[])
    raise typer.Exit(code=code)
