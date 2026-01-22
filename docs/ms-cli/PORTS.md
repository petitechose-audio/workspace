# Ports

## Convention

Host UDP ports (Bitwig extension listens here):

- 9000: hardware (Teensy via serial)
- 9001: native simulator (SDL desktop)
- 9002: wasm simulator (browser)

Controller ports (apps connect here):

- 8000: core native
- 8100: core wasm
- 8001: bitwig native
- 8101: bitwig wasm

Source of truth:

- `config.toml`
- `open-control/bridge/src/constants.rs`
