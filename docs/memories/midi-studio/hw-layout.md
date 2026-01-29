# Hardware Layout Reference

Source of truth for IDs is the code:

- `midi-studio/core/src/config/InputIDs.hpp` (ButtonID / EncoderID)
- `midi-studio/core/src/config/platform-teensy/Hardware.hpp` (pins + MUX wiring)

This doc is a stable reference for planned features (e.g. sequencer mappings).

## Buttons (Config::ButtonID)

Defined in `midi-studio/core/src/config/InputIDs.hpp`.

- Left column
  - `LEFT_TOP` (10)
  - `LEFT_CENTER` (11)
  - `LEFT_BOTTOM` (12)
- Bottom row
  - `BOTTOM_LEFT` (20)
  - `BOTTOM_CENTER` (21)
  - `BOTTOM_RIGHT` (22)
- Macro encoder buttons
  - `MACRO_1..MACRO_8` (31..38)
- Special
  - `NAV` (40) (NAV encoder push)

## Encoders (Config::EncoderID)

Defined in `midi-studio/core/src/config/InputIDs.hpp`.

- Macro encoders
  - `MACRO_1..MACRO_8` (301..308)
- Special encoders
  - `NAV` (400)
  - `OPT` (410)

## Physical hardware

Hardware specs live in `midi-studio/hardware/README.md`.
