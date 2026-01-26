"""Status command - check pending changes in all workspace repos."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ms.cli.context import build_context
from ms.core.result import Err, Ok
from ms.git.repository import GitStatus, Repository

# Force UTF-8 for nice output
_console = Console(force_terminal=True, legacy_windows=False)


def _copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard. Returns True on success."""
    try:
        # Windows
        process = subprocess.Popen(
            ["clip"], stdin=subprocess.PIPE, shell=True
        )
        process.communicate(text.encode("utf-8"))
        return process.returncode == 0
    except Exception:
        return False


@dataclass
class RepoStatus:
    """Status of a single repo."""

    name: str
    path: Path
    status: GitStatus | None
    error: str | None = None

    @property
    def has_changes(self) -> bool:
        if self.status is None:
            return False
        return (
            not self.status.is_clean
            or self.status.ahead > 0
            or self.status.behind > 0
        )


def _collect_repos(root: Path, midi_studio: Path, open_control: Path) -> list[tuple[str, Path]]:
    """Collect all git repos in workspace."""
    repos: list[tuple[str, Path]] = []

    if (root / ".git").exists():
        repos.append(("ms", root))

    if midi_studio.exists():
        for d in sorted(midi_studio.iterdir()):
            if d.is_dir() and (d / ".git").exists():
                repos.append((f"midi-studio/{d.name}", d))

    if open_control.exists():
        for d in sorted(open_control.iterdir()):
            if d.is_dir() and (d / ".git").exists():
                repos.append((f"open-control/{d.name}", d))

    return repos


def _render_counts(st: GitStatus) -> Text:
    """Render change counts with colors."""
    text = Text()

    modified = sum(1 for e in st.entries if e.xy[0] == "M" or e.xy[1] == "M")
    added = sum(1 for e in st.entries if e.xy[0] == "A")
    deleted = sum(1 for e in st.entries if e.xy[0] == "D" or e.xy[1] == "D")
    untracked = st.untracked_count

    parts: list[tuple[str, str]] = []
    if modified:
        parts.append((f"{modified}M", "yellow"))
    if added:
        parts.append((f"{added}A", "green"))
    if deleted:
        parts.append((f"{deleted}D", "red"))
    if untracked:
        parts.append((f"{untracked}?", "cyan"))

    for i, (count, color) in enumerate(parts):
        if i > 0:
            text.append(" ")
        text.append(count, style=color)

    return text


def _render_divergence(st: GitStatus) -> Text:
    """Render ahead/behind."""
    text = Text()
    if st.ahead:
        text.append(f"{st.ahead}", style="green")
        text.append("^", style="green dim")
    if st.ahead and st.behind:
        text.append(" ")
    if st.behind:
        text.append(f"{st.behind}", style="red")
        text.append("v", style="red dim")
    return text


def _render_entry(xy: str, path: str) -> Text:
    """Render a file entry."""
    text = Text("    ")
    if xy == "??":
        text.append("? ", style="cyan")
    elif xy[0] == "M" or xy[1] == "M":
        text.append("M ", style="yellow")
    elif xy[0] == "A":
        text.append("A ", style="green")
    elif xy[0] == "D" or xy[1] == "D":
        text.append("D ", style="red")
    else:
        char = xy[0] if xy[0] != " " else xy[1]
        text.append(f"{char} ")
    text.append(path, style="dim")
    return text


def _render_changed_repo(r: RepoStatus, detailed: bool) -> Text:
    """Render a repo with changes."""
    st = r.status
    assert st is not None

    lines = Text()

    # Line 1: name
    lines.append(r.name, style="bold")
    lines.append("\n")

    # Line 2: path (dim)
    lines.append(str(r.path), style="dim")
    lines.append("\n")

    # Line 3: branch + counts + divergence
    lines.append(st.branch or "?", style="blue")
    lines.append("  ")
    lines.append_text(_render_counts(st))
    div = _render_divergence(st)
    if div.plain:
        lines.append("  ")
        lines.append_text(div)

    # Files if detailed
    if detailed and st.entries:
        lines.append("\n")
        for i, entry in enumerate(st.entries):
            if i > 0:
                lines.append("\n")
            lines.append_text(_render_entry(entry.xy, entry.path))

    return lines


def _generate_plain_text(
    changed: list[RepoStatus], clean: list[RepoStatus], detailed: bool
) -> str:
    """Generate plain text output for clipboard."""
    lines: list[str] = []

    if changed:
        lines.append("PENDING")
        lines.append("")
        for r in changed:
            if r.error:
                lines.append(f"{r.name}")
                lines.append(f"  error: {r.error}")
            else:
                st = r.status
                assert st is not None

                # Counts
                modified = sum(1 for e in st.entries if e.xy[0] == "M" or e.xy[1] == "M")
                added = sum(1 for e in st.entries if e.xy[0] == "A")
                deleted = sum(1 for e in st.entries if e.xy[0] == "D" or e.xy[1] == "D")
                untracked = st.untracked_count

                counts: list[str] = []
                if modified:
                    counts.append(f"{modified}M")
                if added:
                    counts.append(f"{added}A")
                if deleted:
                    counts.append(f"{deleted}D")
                if untracked:
                    counts.append(f"{untracked}?")

                lines.append(f"{r.name}")
                lines.append(f"{r.path}")
                lines.append(f"{st.branch}  {' '.join(counts)}")

                if detailed and st.entries:
                    for entry in st.entries:
                        char = "?" if entry.xy == "??" else entry.xy[0] if entry.xy[0] != " " else entry.xy[1]
                        lines.append(f"  {char} {entry.path}")

            lines.append("")

    if clean:
        lines.append(f"OK ({len(clean)})")
        for r in clean:
            lines.append(f"  {r.name}")

    return "\n".join(lines)


def status(
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show modified files"),
    fetch: bool = typer.Option(False, "--fetch", "-f", help="Fetch remotes first"),
    no_copy: bool = typer.Option(False, "--no-copy", help="Don't copy to clipboard"),
) -> None:
    """Check pending changes in all workspace repos."""
    ctx = build_context()

    repo_list = _collect_repos(
        ctx.workspace.root,
        ctx.workspace.midi_studio_dir,
        ctx.workspace.open_control_dir,
    )

    # Fetch if requested
    if fetch:
        _console.print("[dim]Fetching remotes...[/dim]")
        for _name, path in repo_list:
            Repository(path).fetch()
        _console.print()

    # Collect statuses
    statuses: list[RepoStatus] = []
    for name, path in repo_list:
        repo = Repository(path)
        result = repo.status()
        match result:
            case Err(e):
                statuses.append(RepoStatus(name, path, None, e.message))
            case Ok(st):
                statuses.append(RepoStatus(name, path, st))

    changed = [r for r in statuses if r.has_changes or r.error]
    clean = [r for r in statuses if not r.has_changes and not r.error]

    # Render changed repos
    if changed:
        changed_items: list[Text] = []
        for r in changed:
            if r.error:
                err_text = Text()
                err_text.append(r.name, style="bold red")
                err_text.append(f"\n{r.error}", style="red dim")
                changed_items.append(err_text)
            else:
                changed_items.append(_render_changed_repo(r, detailed))

        # Join with blank lines
        combined = Text()
        for i, item in enumerate(changed_items):
            if i > 0:
                combined.append("\n\n")
            combined.append_text(item)

        panel = Panel(
            combined,
            title="[bold yellow]PENDING[/bold yellow]",
            title_align="left",
            border_style="yellow",
            padding=(0, 1),
        )
        _console.print(panel)
        _console.print()

    # Render clean repos
    if clean:
        clean_text = Text()
        for i, r in enumerate(clean):
            if i > 0:
                clean_text.append("\n")
            clean_text.append(r.name, style="dim")

        panel = Panel(
            clean_text,
            title=f"[bold green]OK[/bold green] [dim]({len(clean)})[/dim]",
            title_align="left",
            border_style="green dim",
            padding=(0, 1),
        )
        _console.print(panel)

    if not changed and not clean:
        _console.print("[dim]No repos found[/dim]")

    # Copy to clipboard by default
    if not no_copy:
        plain = _generate_plain_text(changed, clean, detailed)
        if _copy_to_clipboard(plain):
            _console.print("\n[dim]Copied to clipboard[/dim]")
