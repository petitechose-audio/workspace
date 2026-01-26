"""Core app command - hardware and simulator builds."""

from __future__ import annotations

from enum import Enum, auto

import typer

from ms.cli.context import build_context
from ms.core.app import resolve
from ms.core.errors import ErrorCode
from ms.core.result import Err, Ok
from ms.output.console import Style
from ms.services.build import BuildService
from ms.services.hardware import HardwareService


class Mode(Enum):
    """Build mode for core app."""

    HW_FULL = auto()  # build + upload + monitor (default)
    HW_BUILD = auto()  # build only
    HW_UPLOAD = auto()  # build + upload
    SIM_NATIVE = auto()  # native simulator
    SIM_WEB = auto()  # wasm simulator


def _resolve_mode(build: bool, upload: bool, native: bool, web: bool) -> Mode:
    """Determine build mode from CLI flags."""
    match (build, upload, native, web):
        case (_, _, True, _):
            return Mode.SIM_NATIVE
        case (_, _, _, True):
            return Mode.SIM_WEB
        case (True, _, _, _):
            return Mode.HW_BUILD
        case (_, True, _, _):
            return Mode.HW_UPLOAD
        case _:
            return Mode.HW_FULL


def core(
    build: bool = typer.Option(False, "--build", help="HW: build only"),
    upload: bool = typer.Option(False, "--upload", help="HW: build + upload"),
    native: bool = typer.Option(False, "--native", help="Sim: build + run"),
    web: bool = typer.Option(False, "--web", help="Sim: build + serve"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without modifying"),
) -> None:
    """Build/run core app.

    Modes (mutually exclusive, first match wins):
      --native  Simulator: native build + run
      --web     Simulator: WASM build + serve
      --build   Hardware: build only
      --upload  Hardware: build + upload
      (default) Hardware: build + upload + monitor
    """
    ctx = build_context()

    result = resolve("core", ctx.workspace.root)
    match result:
        case Err(e):
            ctx.console.error(e.message)
            if e.available:
                ctx.console.print(f"Available: {', '.join(e.available)}", Style.DIM)
            raise typer.Exit(code=int(ErrorCode.USER_ERROR))
        case Ok(app):
            pass

    mode = _resolve_mode(build, upload, native, web)

    match mode:
        case Mode.SIM_NATIVE:
            build_svc = BuildService(
                workspace=ctx.workspace,
                platform=ctx.platform,
                config=ctx.config,
                console=ctx.console,
            )
            code = build_svc.run_native(app_name="core")
            raise typer.Exit(code=code)

        case Mode.SIM_WEB:
            build_svc = BuildService(
                workspace=ctx.workspace,
                platform=ctx.platform,
                config=ctx.config,
                console=ctx.console,
            )
            code = build_svc.serve_wasm(app_name="core")
            raise typer.Exit(code=code)

        case Mode.HW_BUILD:
            hw = HardwareService(
                workspace=ctx.workspace,
                platform=ctx.platform,
                config=ctx.config,
                console=ctx.console,
            )
            result = hw.build(app, dry_run=dry_run)
            match result:
                case Err(e):
                    ctx.console.error(e.message)
                    if e.hint:
                        ctx.console.print(f"hint: {e.hint}", Style.DIM)
                    raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))
                case Ok(_):
                    pass

        case Mode.HW_UPLOAD:
            hw = HardwareService(
                workspace=ctx.workspace,
                platform=ctx.platform,
                config=ctx.config,
                console=ctx.console,
            )
            # oc-upload does build + upload
            result = hw.upload(app, dry_run=dry_run)
            match result:
                case Err(e):
                    ctx.console.error(e.message)
                    if e.hint:
                        ctx.console.print(f"hint: {e.hint}", Style.DIM)
                    raise typer.Exit(code=int(ErrorCode.BUILD_ERROR))
                case Ok(_):
                    pass

        case Mode.HW_FULL:
            hw = HardwareService(
                workspace=ctx.workspace,
                platform=ctx.platform,
                config=ctx.config,
                console=ctx.console,
            )
            # oc-monitor does build + upload + monitor
            code = hw.monitor(app)
            raise typer.Exit(code=code)
