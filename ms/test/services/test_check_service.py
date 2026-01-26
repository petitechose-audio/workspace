from __future__ import annotations

from pathlib import Path

from ms.core.config import BitwigPathsConfig, Config
from ms.core.workspace import Workspace
from ms.platform.detection import Arch, LinuxDistro, Platform, PlatformInfo
from ms.services.check import CheckService


def test_check_service_resolves_bitwig_paths_from_config(tmp_path: Path) -> None:
    ws = Workspace(root=tmp_path)
    platform = PlatformInfo(platform=Platform.WINDOWS, arch=Arch.X64, distro=LinuxDistro.UNKNOWN)
    cfg = Config(bitwig=BitwigPathsConfig(windows="C:/X"))

    service = CheckService(workspace=ws, platform=platform, config=cfg)
    assert service.resolve_bitwig_paths() == {"windows": "C:/X"}
