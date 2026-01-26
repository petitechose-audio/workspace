from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import typer

from ms.cli.context import build_context
from ms.core.config import CONTROLLER_CORE_NATIVE_PORT
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.output.errors import build_error_exit_code, print_build_error
from ms.services.build import BuildService

if TYPE_CHECKING:
    from ms.cli.context import CLIContext

VALID_TARGETS = ("native", "wasm")


def _validate_target(target: str, ctx: "CLIContext") -> Literal["native", "wasm"] | None:
    """Validate target argument, return None if invalid."""
    if target in VALID_TARGETS:
        return target  # type: ignore[return-value]

    ctx.console.error(f"Unknown target: {target}")
    ctx.console.print(f"Available: {', '.join(VALID_TARGETS)}", Style.DIM)
    return None


def build(
    app_name: str = typer.Argument(..., help="App: core, bitwig, ..."),
    target: str = typer.Argument(..., help="Target: native|wasm"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying."),
) -> None:
    """Build native or WASM simulator."""
    ctx = build_context()

    # Validate target early with clear error message
    validated_target = _validate_target(target, ctx)
    if validated_target is None:
        raise typer.Exit(code=int(ErrorCode.USER_ERROR))

    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )

    if validated_target == "native":
        result = service.build_native(app_name=app_name, dry_run=dry_run)
    else:  # wasm
        result = service.build_wasm(app_name=app_name, dry_run=dry_run)

    match result:
        case Ok(output_path):
            ctx.console.success(str(output_path))
        case Err(error):
            print_build_error(error, ctx.console)
            raise typer.Exit(code=build_error_exit_code(error))


def run(
    app_name: str = typer.Argument(..., help="App: core, bitwig, ..."),
) -> None:
    """Build and run native simulator."""
    ctx = build_context()
    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    code = service.run_native(app_name=app_name)
    raise typer.Exit(code=code)


def web(
    app_name: str = typer.Argument(..., help="App: core, bitwig, ..."),
    port: int = typer.Option(CONTROLLER_CORE_NATIVE_PORT, "--port", "-p", help="HTTP server port"),
) -> None:
    """Build and serve WASM simulator."""
    ctx = build_context()
    service = BuildService(
        workspace=ctx.workspace,
        platform=ctx.platform,
        config=ctx.config,
        console=ctx.console,
    )
    code = service.serve_wasm(app_name=app_name, port=port)
    raise typer.Exit(code=code)
