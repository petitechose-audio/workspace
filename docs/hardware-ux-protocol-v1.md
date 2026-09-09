# Isolated hardware UX benchmark, protocol v1

This is an opt-in Core diagnostic firmware profile (`MS_HARDWARE_BENCHMARK`),
not a remote replay facility for normal firmware or an existing user session.
Settings are RAM-only and product storage is unavailable from boot. The fixture
is versioned code, not an uploaded `.mspj`. One run consumes one boot; rebooting
resets process-global RNG/state. It does not make USB/CPU timing deterministic.

## Existing transport, explicit device

Use the bridge's existing localhost TCP control port. The bridge keeps ownership
of USB serial. First send `{"schema":1,"cmd":"info"}\n`, verify `ok`,
`paused:false`, `serial_open:true`, exact `controller_serial`, `control_port`, and
retain `instance_id`. Never open serial directly, start another bridge, pause the
Manager bridge, bind its log socket, or send benchmark packets to host UDP.
UDP tracks its last sender and would redirect DAW replies to a benchmark client.

Binary requests use the existing 16-byte OCRQ header: `"OCRQ"`, version `u8=1`,
expected response `u8=0xDF`, token `u16`, timeout milliseconds `u32`, payload bytes
`u32`. OCRS responses: `"OCRS"`, version `u8=1`, bridge status `u8`, token `u16`,
payload bytes `u32`, message bytes `u16`, reserved `u16=0`; payload then UTF-8
message. All integers are little-endian. Bridge status must be zero. TCP reads
must handle fragmentation and enforce size bounds.

Application request: `[0xDE,0,1,requestId:u16,operation:u8,body...]`.
Application response: `[0xDF,0,1,requestId:u16,status:u8,JSON object UTF-8...]`.
The zero byte is the Serial8 empty message-name length, followed by schema 1.
There is **no operation byte in the response**. Bridge correlation already
supports arbitrary response ID plus request ID. Statuses: 0 OK, 1 invalid
argument, 2 invalid state, 3 not ready, 4 too large, 5 conflict, 6 unsupported.

DE/DF are reserved by this benchmark contract, not the generic code generator:
Bitwig currently uses 00–5B and its allocator can grow through FF; filesystem
uses E0–FB and filesystem jobs FC/FD. Do not insert benchmark messages into the
alphabetically allocated Bitwig message list. Guard collisions when that list
changes. Existing bridges quarantine late FD job replies but not late DF replies;
a DF reply arriving after its waiter timed out can reach the DAW host path.
Run this dedicated profile without DAW traffic. No bridge upgrade is required
for ordinary matching requests/responses.

## Operations and bounded payloads

| Op | Name | Request body |
|---:|---|---|
| 0 | HELLO | Empty |
| 1 | UPLOAD | run ID `u32`, count `u16`, duration µs `u32`, maximum lateness µs `u32`, records |
| 2 | START | run ID `u32` |
| 3 | STATUS | Empty |
| 4 | RESULT | run ID `u32`, section `u8`, index `u16` |
| 5 | CANCEL | run ID `u32` |
| 6 | REBOOT | Empty; acknowledge before MCU reboot |

HELLO includes `benchmark:true`, `protocol:1`, `build_id`, `fixture`,
`fixture_version`, `max_events:2048`, `state`, `run_id`, `ram_only:true`,
`requires_reboot:true`. `build_id` is a firmware source fingerprint, **not**
a claim that the firmware knows the uploaded HEX hash. The host records this
identity and the SHA-256 of original script bytes separately.

Limits: 2,048 records, duration 1–120,000,000 µs, maximum lateness 0–1,000,000 µs.
Each record is exactly 12 bytes: `dueUs:u32, kind:u8, reserved:u8=0,
target:u16, value:i32`. Kind 1 is button value 0/1, kind 2 encoder value in milli
units, kind 3 marker with numeric target label ID, kind 4 assert view (`target=0`,
value Core ViewType 0–4), kind 5 assert mode (`target=0`, value bits are FNV-1a
32 of the exact UTF-8 mode name), kind 6 transport (`target=0`, value stop 0/start 1),
kind 7 foreground block (`target=0`, value 1–1,000,000 microseconds). Blocks must
fit the run duration; no subsequent record may fall inside a block interval.
Upload ACK includes `run_id`, `count`, `script_fnv1a` (unsigned JSON integer,
FNV-1a 32 over the **records only**, offset basis 2166136261, prime 16777619).
Idempotent duplicate upload also compares count, duration and maximum lateness;
the same ID cannot replace a different script. START is idempotent for its ID.

START arms for 500 ms, then the MCU dispatches from its own clock, with original
absolute due times and stable ordering for ties. The host sends no polls until
duration + configured maximum lateness + 750 ms (arm and cleanup) have elapsed
since START acknowledgement. State is idle/uploaded/armed/running/finishing/completed/cancelled/failed.
Terminal states require reboot before another trial. CANCEL must release injected
buttons and stop the benchmark transport. A timeout is not proof of cancellation.

RESULT sections: 0 summary (index 0), 1 event record (index), 2 metric (index),
3 LVGL aggregate (index 0 totals, 1 worst, 2 last), 4 memory (index). Summary
contains `run_id`, terminal `state`, `ok`, `event_count` (available executed
records), `uploaded_count` (full script), `metric_count`, `memory_count` (currently
1). No unbounded result message or continuous serial trace during measurement.

## CLI and .ux subset

```
ms ux hardware status --serial 18040250 --control-port 8001
ms ux hardware run benchmark.ux --serial 18040250 --control-port 8001 --output-root .bench/run-a --fresh --repeat 3
ms ux hardware cancel 123 --serial 18040250 --control-port 8001
ms ux hardware reboot --serial 18040250 --control-port 8001
```

These commands do not build or flash. The serial and control port are mandatory;
the example selects Elegoo only in the presently documented Manager bindings.
The output destination must not exist. Every trial stores manifest, summary,
NDJSON records and, on failure, partial evidence/error details. `--repeat` reboots
only verified benchmark firmware between trials and checks the same build and
fixture return. `--fresh` explicitly permits this before the first trial.

`summary.json` is the firmware verdict, **not proof of complete extraction**.
Only `completion.json` certifies collection: it is written after the NDJSON file
is closed, every page is validated, and a second summary is unchanged. It contains
`collection_complete:true`, `benchmark_ok` (the separate firmware verdict), and
`run_id`. Consumers must require this file and matching run IDs; absent or malformed
completion means incomplete evidence, even if a retained summary says `ok:true`.
The host checks script/event cardinality and duration, the single memory page,
event indices and monotonic dispatch timing, unique metric names, exact 33-bin
histograms summing to sample counts, timing totals, and matching LVGL aggregates
and phase names. Invalid or interrupted extraction retains `error.json` and partial
pages but never certifies completion. A complete failed benchmark remains useful
evidence (`benchmark_ok:false`); requested repetitions continue after reboot, and
the CLI exits unsuccessfully if any trial fails. Collection/protocol failure stops
remaining repetitions instead of silently retrying or discarding a trial.

The compiler accepts integer millisecond timestamps, comments `#` or `//`,
`button ID down|up|press|release`, `tap ID [durationMs]` (default 60),
`encoder_value ID VALUE`, `tick`, `wait`. It preserves native stable timestamp
ordering and validates paired button transitions. Encoder values must fit signed
milli-units exactly: no float approximation or hidden truncation. Physical input
IDs match device-support v1 (buttons 10–40; encoders 301–308/400/410).

`capture screen|controller NAME` becomes a **semantic marker, not an image**;
the manifest preserves the original label/scope. Explicit benchmark extensions
are `marker NAME`, `assert_view MACRO|CLIPS|PROJECT|DEVICE_SETTINGS|MODULATORS`,
`assert_mode EXACT_MODE_NAME`, and `transport start|stop`. `scenario NAME` is
accepted only once at timestamp zero and must exactly match HELLO.fixture; it
does not mutate fixture state. `tick/wait` set a duration boundary, not an
extra forced LVGL frame. `block_foreground MS` (1–1000 integer milliseconds)
deliberately stalls the Teensy foreground with interrupts enabled: no yield,
delay, input poll or output service is called inside the loop. It is restricted
to the isolated hardware profile; native execution explicitly fails rather
than simulating a timing result. `benchmark.foreground-block` records elapsed
time, requested microseconds (unit A), and the number of USB admission-age
samples produced during the block (unit B, service batches, not MIDI packets
or host acknowledgements). Duration defaults to final timestamp plus 1 second;
`--duration-ms` can specify it explicitly. All other syntax, especially relative
`encoder`, arbitrary scenarios, extra arguments and unsupported assertions, is
rejected before any connection. Native `# Expect` comments are not executable
hardware assertions; use the explicit assert directives above.

The versioned workloads live in `midi-studio/core/script/bench`, outside
the SDL workflow catalog because benchmark assertions are not native SDL syntax:

| Script | Duration | Events | Records FNV-1a |
|---|---:|---:|---|
| idle-playback.ux | 10 s | 11 | e954535b |
| modulator-transitions.ux | 20 s | 108 | 22e86618 |
| macro-edit.ux | 20 s | 67 | 52d2f5bb |

`foreground-isolation.ux` adds 100, 250 and 1000 ms foreground blocks during
internal-clock playback. Require successful extraction and inspect output
queue/wake latency and timer gaps, not merely the script's scheduling verdict.
This demonstrates firmware-side service during stalls, not host receipt timing.

Use `--max-lateness-us 1000000` for the initial baseline with known ~207 ms stalls.
The default 100000 µs is an explicit stricter scheduling acceptance criterion.
View and semantic-mode assertions check the selected route at the marked targets.
For a state-only capture at the Macro root, the benchmark projects
`macro.performance`; the normal recorder's event-specific surfaces otherwise
do not describe this idle context. This does not inject an input event.

Recorder-derived input remains quantized and timestamps are recorder flush time,
not raw hardware acquisition time. This bench reproduces that bounded normalized
input stream, not missing DAW MIDI/clock/USB timing or a previous live session.
