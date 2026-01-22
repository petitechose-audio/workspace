# Prerequisites

This workspace targets Linux / macOS / Windows (via Git Bash).

## Required (all platforms)

- Git
- GitHub CLI (`gh`) authenticated: `gh auth login`
- curl, tar, unzip

## Linux

- SDL2 dev packages
- ALSA dev packages
- pkg-config

Examples:

- Fedora/RHEL:
  - `sudo dnf install SDL2-devel alsa-lib-devel pkgconf-pkg-config`
- Ubuntu/Debian:
  - `sudo apt install libsdl2-dev libasound2-dev pkg-config`

Optional but recommended:

- Rust (for building `oc-bridge`): https://rustup.rs
- Bitwig Studio (for the extension)

## macOS

- Homebrew
- SDL2: `brew install sdl2`

Optional but recommended:

- Rust (for building `oc-bridge`): https://rustup.rs
- Bitwig Studio

## Windows

- Git for Windows (Git Bash)
- Recommended installs via winget:
  - `winget install Git.Git`
  - `winget install GitHub.cli`

Optional but recommended:

- Bitwig Studio
