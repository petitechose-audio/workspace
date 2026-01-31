# Phase 04: ms-manager Foundation (Tauri + Svelte) - Fetch/Verify/Cache

Status: TODO

## Goal

Create `ms-manager` as the end-user GUI that:

- installs latest stable bundle by default
- supports advanced channel + tag selection
- downloads with caching
- verifies manifest signature and asset sha256
- stages installs into `versions/<tag>/` and switches `current/`

This phase focuses on the foundation (network + storage + verification + minimal UI).

## Repo Setup

- New public repo: `petitechose-midi-studio/ms-manager`
- Stack:
  - Tauri (Rust backend)
  - Svelte (lightweight UI)

## Core Architecture

Backend (Rust):
- `dist_client`:
  - fetch latest stable manifest via GitHub Releases `latest` endpoint
  - list available releases for rollback via GitHub Releases API
  - download assets (with caching)
- `verify`: Ed25519 signature verify + sha256 verify
- `storage`: install roots, cache, versions/current
- `ops`: install/update transactions (Phase 05 will finalize)

Frontend (Svelte):
- Simple mode: one button “Install latest stable”
- Advanced mode:
  - select channel
  - list tags via GitHub Releases API (fallback: installed local versions)
  - install selected tag

## Install Roots (v1)

- Windows:
  - App installed via installer.
  - Payload root: `C:\ProgramData\MIDI Studio\`.
- macOS:
  - Payload root: `~/Library/Application Support/MIDI Studio/`.
- Linux:
  - Payload root: `~/.local/share/midi-studio/`.

Within payload root:
- `versions/<tag>/...`
- `current -> versions/<tag>` (symlink/junction)
- `state/state.json`
- `logs/`

## Exit Criteria

- App runs on all target OS.
- Can fetch latest stable manifest from:
  - `https://github.com/petitechose-midi-studio/distribution/releases/latest/download/manifest.json`
  - `https://github.com/petitechose-midi-studio/distribution/releases/latest/download/manifest.json.sig`
- Verifies manifest signature and asset sha256.
- Stores downloaded assets in a cache and reuses it.

## Notes (recorded)

Public keys (Ed25519, base64, 32 bytes):
- stable/release: `2rHtM99leFGTpjZ8fZHNCdGXlEKmAw6hEyaat1uGO3M=`
- nightly: `voOksaS+NoUkEy9c8YunbTwPnb1dlXCyEJ9Yy07233A=`

## Tests

Local (fast):
- Rust unit tests:
  - manifest signature verification (test key)
  - sha256 verification
  - path resolution per OS

Local (full):
- `cargo test`
- Tauri dev run + install simulation using local fake distribution server.
