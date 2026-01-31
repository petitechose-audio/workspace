# Phase 01: Release Spec + Manifest v2 + Signing + Anti-rollback

Status: TODO

## Goal

Define and implement the distribution contracts consumed by `ms-manager`:

- `release-spec.json` (build inputs)
- `manifest.json` (bundle outputs)
- `manifest.json.sig` (Ed25519 signature)
- anti-rollback and revocation rules

This phase must be finished before we write the distribution CI.

## Design Principles

- Single source of truth: the distribution repo is the only end-user feed.
- Everything is explicit: exact SHAs/tags per component.
- Minimal boilerplate: one schema, one signature, deterministic filenames.
- Security first:
  - signature required
  - sha256 required
  - prevent silent downgrade/rollback

## Deliverables

1) `release-spec.json` schema (inputs)

Required fields (suggested):
- `schema`: integer
- `channel`: stable|beta|nightly
- `tag`: bundle tag
- `repos`: list of pinned repos:
  - `{ id, url, ref, sha, required_ci_workflow }`

Notes:
- Some repos may be Ubuntu-only in CI (e.g. firmware + Bitwig extension). That is still “CI passed”
  if the canonical CI workflow covers the required deliverables.
- `build`: options:
  - OS/arch matrix
  - whether to build firmware/extension

2) `manifest.json` schema v2 (outputs)

Required fields (suggested):
- `schema`: 2
- `channel`, `tag`, `published_at`
- `assets[]`: `{ id, kind, os, arch, filename, size, sha256 }`
- `repos[]`: `{ id, url, sha }` (pins for audit)
- `install_sets`: at least `default`
- `pages`: demo URLs per channel/tag

3) Signature format

- `manifest.json.sig`: Ed25519 detached signature over the exact bytes of `manifest.json`.
- `ms-manager` embeds the public key.
- CI holds the private key as a secret.

4) Anti-rollback policy

- Default install/update must never auto-downgrade.
- Downgrade only allowed from Advanced UI with explicit confirmation.
- Optional: `revoked.json` feed to block known-bad tags (signed or pinned in repo).

## Implementation Plan (recommended)

1) Put the canonical JSON schemas in the distribution repo (not ms-dev-env).
   - `schemas/release-spec.schema.json`
   - `schemas/manifest.schema.json`

2) Implement a small, testable “manifest tool” in Rust (recommended) OR Python.
   - Inputs: `release-spec.json` + dist directory of produced assets
   - Output: `manifest.json`
   - Command: `ms-dist-manifest build --spec release-spec.json --dist dist/ --out manifest.json`

3) Add signing tool step in CI.
   - `ms-dist-manifest sign --in manifest.json --out manifest.json.sig --key-env MS_DIST_ED25519_SK`

4) Add verification library used by ms-manager.
   - `verify_manifest(manifest, sig, pk) -> ok/err`
   - `verify_assets(sha256)`

## Exit Criteria

- Schemas exist and are versioned.
- A tool can generate a manifest from known artifacts.
- Signature is generated and verified locally.
- Anti-rollback rules are clearly implemented in the verification logic.

## Tests

Local (fast):
- Schema validation of a sample `release-spec.json` and `manifest.json`.
- Signature verify test with a test key.

Local (full):
- End-to-end local run:
  - create fake assets directory
  - generate manifest
  - sign
  - verify signature + sha256
