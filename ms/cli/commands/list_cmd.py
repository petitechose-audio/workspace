"""List command - show buildable apps."""

from __future__ import annotations

from ms.cli.context import build_context
from ms.core.app import list_all, resolve
from ms.core.result import Err, Ok
from ms.output.console import Style


def list_apps() -> None:
    """List buildable apps in the workspace."""
    ctx = build_context()

    names = list_all(ctx.workspace.root)
    if not names:
        ctx.console.warning("no apps found (missing midi-studio/?)")
        return

    ctx.console.header("apps")
    for name in names:
        match resolve(name, ctx.workspace.root):
            case Ok(app):
                caps: list[str] = []
                if app.has_sdl:
                    caps.append("sdl")
                if app.has_teensy:
                    caps.append("teensy")

                suffix = f" ({', '.join(caps)})" if caps else ""
                ctx.console.print(f"- {app.name}{suffix}")
            case Err(_):
                # list_all() should only yield resolvable apps; stay defensive.
                ctx.console.print(f"- {name}", Style.DIM)
