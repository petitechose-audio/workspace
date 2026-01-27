# SPDX-License-Identifier: MIT
"""Pinned minimum tool versions.

Keep this file small and explicit.

We use "minimum versions" (MSRV-style) rather than pinning exact versions,
to reduce maintenance while staying reproducible enough for contributors.
"""

from __future__ import annotations

__all__ = [
    "RUST_MIN_VERSION",
    "RUST_MIN_VERSION_TEXT",
]


# Rust toolchain minimum (MSRV).
# Update when we adopt language/features that require a newer stable.
RUST_MIN_VERSION = (1, 93, 0)
RUST_MIN_VERSION_TEXT = "1.93.0"
