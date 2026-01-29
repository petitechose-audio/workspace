# OpenControl

This folder contains cross-repo notes about the OpenControl ecosystem as used by the `ms-dev-env` workspace.

In this workspace, OpenControl is a set of git repos under `open-control/` (see `ms/data/repos.toml`).

## Repos (workspace view)

- `open-control/bridge` - `oc-bridge` (TUI + service mode + transports)
- `open-control/framework` - core framework (state, UI patterns, input binding, etc.)
- `open-control/hal-*` - HAL implementations (sdl, teensy, midi, net)
- `open-control/ui-lvgl*` - LVGL UI runtime + components
- `open-control/protocol-codegen` - code generation for controller/host protocol

## Where to look

- Bridge ports/conventions: `open-control/bridge/src/constants.rs`
- WebSocket transport binding behavior: `open-control/bridge/src/transport/websocket.rs`
