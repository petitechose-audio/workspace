from __future__ import annotations

import os
from pathlib import Path

from ms.services.dist import package_platform


def test_package_platform_handles_epoch_mtime(tmp_path: Path) -> None:
    # Minimal workspace structure
    (tmp_path / "bin" / "bridge").mkdir(parents=True)
    (tmp_path / "bin" / "core" / "native").mkdir(parents=True)
    (tmp_path / "bin" / "bitwig" / "native").mkdir(parents=True)
    (tmp_path / "dist").mkdir()

    # Create a tool file with an epoch mtime (1970), which would normally break ZIP.
    tool_dir = tmp_path / ".ms" / "platformio" / "packages" / "tool-teensy"
    tool_dir.mkdir(parents=True)
    uploader = tool_dir / "teensy_loader_cli"
    uploader.write_bytes(b"cli")
    os.utime(uploader, (0, 0))

    created = package_platform(
        workspace_root=tmp_path,
        out_dir=tmp_path / "dist",
        require_uploader=True,
    )

    # We should at least get the uploader bundle and native bundle (even if empty-ish).
    assert any(p.name.endswith("-teensy-uploader.zip") for p in created)
