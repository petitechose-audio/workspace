"""Bounded, RAM-only hardware UX runs through the bridge's existing control socket."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import socket
import struct
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ms.core.structured import StrDict, as_obj_list, as_str_dict

REQUEST_ID = 0xDE
RESPONSE_ID = 0xDF
MAX_EVENTS = 2048
MAX_DURATION_US = 120_000_000
MAX_LATENESS_US = 1_000_000
RECORD = struct.Struct("<IBBHi")
BUTTONS = {
    "LEFT_TOP": 10,
    "LEFT_CENTER": 11,
    "LEFT_BOTTOM": 12,
    "BOTTOM_LEFT": 20,
    "BOTTOM_CENTER": 21,
    "BOTTOM_RIGHT": 22,
    **{f"MACRO_{i}": 30 + i for i in range(1, 9)},
    "NAV": 40,
}
ENCODERS = {**{f"MACRO_{i}": 300 + i for i in range(1, 9)}, "NAV": 400, "OPT": 410}
VIEWS = {"MACRO": 0, "CLIPS": 1, "PROJECT": 2, "DEVICE_SETTINGS": 3, "MODULATORS": 4}


class HardwareUxError(ValueError):
    """Invalid script, identity mismatch, or failed benchmark protocol operation."""


def fnv1a(data: bytes) -> int:
    value = 2166136261
    for byte in data:
        value = ((value ^ byte) * 16777619) & 0xFFFFFFFF
    return value


@dataclass(frozen=True)
class HardwareScript:
    records: bytes
    duration_us: int
    sha256: str
    fixture: str | None
    events: tuple[StrDict, ...]

    @property
    def count(self) -> int:
        return len(self.events)

    def upload(self, run_id: int, max_lateness_us: int) -> bytes:
        if not 0 < run_id <= 0xFFFFFFFF or not 0 <= max_lateness_us <= MAX_LATENESS_US:
            raise HardwareUxError("run ID or maximum lateness outside protocol bounds")
        return (
            struct.pack("<IHII", run_id, self.count, self.duration_us, max_lateness_us)
            + self.records
        )


def _uint(text: str) -> int:
    if not text.isascii() or not text.isdigit():
        raise HardwareUxError(f"expected unsigned integer, got {text!r}")
    return int(text)


def compile_script(path: Path, *, duration_ms: int | None = None) -> HardwareScript:
    """Compile the documented .ux subset; never approximate encoder deltas/scenarios."""
    raw = path.read_bytes()
    rows: list[tuple[int, int, int, int, StrDict]] = []
    fixture: str | None = None
    end_us = 0
    marker_id = 0
    for line_number, raw_line in enumerate(raw.decode("utf-8-sig").splitlines(), 1):
        line = re.split(r"#|//", raw_line, maxsplit=1)[0].strip()
        if not line:
            continue
        try:
            fields = line.split()
            if len(fields) < 2:
                raise HardwareUxError("expected `<milliseconds> <command>`")
            due = _uint(fields[0]) * 1000
            command, args = fields[1].lower(), fields[2:]
            if due > MAX_DURATION_US:
                raise HardwareUxError("timestamp exceeds 120 seconds")
            end_us = max(end_us, due)

            def add(
                kind: int,
                target: int,
                value: int,
                at: int = due,
                source_line: int = line_number,
                source_command: str = command,
                **extra: object,
            ) -> None:
                rows.append(
                    (
                        at,
                        kind,
                        target,
                        value,
                        {
                            "line": source_line,
                            "command": source_command,
                            **extra,
                        },
                    )
                )

            if command == "button" and len(args) == 2:
                states = {"down": 1, "press": 1, "up": 0, "release": 0}
                add(1, BUTTONS[args[0].upper()], states[args[1].lower()])
            elif command == "tap" and len(args) in (1, 2):
                hold = _uint(args[1]) if len(args) == 2 else 60
                if hold == 0 or due + hold * 1000 > MAX_DURATION_US:
                    raise HardwareUxError("tap must have positive duration within 120 seconds")
                target = BUTTONS[args[0].upper()]
                add(1, target, 1)
                add(1, target, 0, due + hold * 1000)
                end_us = max(end_us, due + hold * 1000)
            elif command == "encoder_value" and len(args) == 2:
                milli = Decimal(args[1]) * 1000
                if (
                    not milli.is_finite()
                    or milli != milli.to_integral_value()
                    or not -2147483648 <= milli <= 2147483647
                ):
                    raise HardwareUxError(
                        "encoder_value must be exactly representable as signed milli-units"
                    )
                add(2, ENCODERS[args[0].upper()], int(milli))
            elif (
                command == "capture"
                and len(args) == 2
                and args[0].lower() in ("screen", "controller")
            ):
                marker_id += 1
                add(3, marker_id, 0, label=args[1], scope=args[0].lower())
            elif command == "marker" and len(args) == 1:
                marker_id += 1
                add(3, marker_id, 0, label=args[0])
            elif command == "assert_view" and len(args) == 1:
                add(4, 0, VIEWS[args[0].upper()])
            elif command == "assert_mode" and len(args) == 1:
                hashed = fnv1a(args[0].encode("utf-8"))
                add(
                    5,
                    0,
                    hashed if hashed < 0x80000000 else hashed - 0x100000000,
                    expected_mode=args[0],
                )
            elif command == "transport" and len(args) == 1:
                add(6, 0, {"stop": 0, "start": 1}[args[0].lower()])
            elif command == "block_foreground" and len(args) == 1:
                block_us = _uint(args[0]) * 1000
                if not 0 < block_us <= 1_000_000 or due + block_us > MAX_DURATION_US:
                    raise HardwareUxError("foreground block must be 1..1000 ms within the run")
                add(7, 0, block_us)
                end_us = max(end_us, due + block_us)
            elif command in ("tick", "wait") and not args:
                pass  # The autonomous loop already ticks; this sets the duration boundary.
            elif command == "scenario" and len(args) == 1 and due == 0 and fixture is None:
                fixture = args[0]  # Must match the firmware fixture before any upload.
            else:
                raise HardwareUxError(f"unsupported hardware command or arguments: {command!r}")
        except (KeyError, InvalidOperation, HardwareUxError) as exc:
            raise HardwareUxError(f"line {line_number}: {exc}") from exc
        if len(rows) > MAX_EVENTS:
            raise HardwareUxError(f"script exceeds {MAX_EVENTS} events")
    if not rows:
        raise HardwareUxError("script contains no hardware events")
    duration = end_us + 1_000_000 if duration_ms is None else duration_ms * 1000
    if not 0 < duration <= MAX_DURATION_US or duration < end_us:
        raise HardwareUxError("duration must cover every action and fit within 120 seconds")
    rows.sort(key=lambda row: row[0])  # Stable ordering matches the native .ux parser.
    held: set[int] = set()
    events: list[StrDict] = []
    records = bytearray()
    blocked_until = 0
    for due, kind, target, value, metadata in rows:
        if due < blocked_until:
            raise HardwareUxError(f"line {metadata['line']}: action overlaps a foreground block")
        if kind == 7:
            blocked_until = due + value
        if kind == 1:
            if bool(value) == (target in held):
                raise HardwareUxError(f"line {metadata['line']}: unbalanced button transition")
            if value:
                held.add(target)
            else:
                held.remove(target)
        records.extend(RECORD.pack(due, kind, 0, target, value))
        events.append({"due_us": due, "kind": kind, "target": target, "value": value, **metadata})
    if held:
        raise HardwareUxError("script ends with held buttons; add matching releases")
    return HardwareScript(
        bytes(records), duration, hashlib.sha256(raw).hexdigest(), fixture, tuple(events)
    )


def _json_object(data: bytes) -> StrDict:
    value: object = json.loads(data)
    result = as_str_dict(value)
    if result is None:
        raise HardwareUxError("expected a JSON object from the bridge/controller")
    return result


def _receive(stream: socket.socket, count: int) -> bytes:
    data = bytearray()
    while len(data) < count:
        chunk = stream.recv(count - len(data))
        if not chunk:
            raise HardwareUxError("bridge closed a truncated response")
        data.extend(chunk)
    return bytes(data)


class HardwareClient:
    """One explicit device, no bridge spawning, UDP peer changes, or serial takeover."""

    def __init__(self, control_port: int, serial: str) -> None:
        if not 1 <= control_port <= 65535 or not serial.strip():
            raise HardwareUxError("an explicit control port and controller serial are required")
        self.control_port = control_port
        self.serial = serial
        self.request_id = secrets.randbelow(65535)
        self.bridge_info: StrDict = {}

    def verify_bridge(self) -> StrDict:
        with socket.create_connection(("127.0.0.1", self.control_port), timeout=3) as stream:
            stream.sendall(b'{"schema":1,"cmd":"info"}\n')
            with stream.makefile("rb") as reader:
                data = reader.readline(32769)
        if len(data) > 32768 or not data.endswith(b"\n"):
            raise HardwareUxError("invalid bridge info response")
        info = _json_object(data)
        if (
            info.get("ok") is not True
            or info.get("paused") is not False
            or info.get("serial_open") is not True
            or info.get("controller_serial") != self.serial
            or info.get("control_port") != self.control_port
            or not isinstance(info.get("instance_id"), str)
        ):
            raise HardwareUxError(
                "bridge is unavailable or controller identity does not match --serial"
            )
        self.bridge_info = info
        return info

    def rpc(self, operation: int, body: bytes = b"") -> StrDict:
        self.request_id = self.request_id % 65535 + 1
        payload = struct.pack("<BBBHB", REQUEST_ID, 0, 1, self.request_id, operation) + body
        request = struct.pack(
            "<4sBBHII", b"OCRQ", 1, RESPONSE_ID, self.request_id, 3000, len(payload)
        )
        with socket.create_connection(("127.0.0.1", self.control_port), timeout=4) as stream:
            stream.sendall(request + payload)
            header = _receive(stream, 16)
            magic, version, status, token, size, message_size, reserved = struct.unpack(
                "<4sBBHIHH", header
            )
            if (
                magic != b"OCRS"
                or version != 1
                or token != self.request_id
                or reserved != 0
                or size > 32768
                or message_size > 4096
            ):
                raise HardwareUxError("invalid or oversized bridge RPC response")
            response = _receive(stream, size)
            message = _receive(stream, message_size).decode("utf-8", errors="replace")
        if status:
            raise HardwareUxError(f"bridge RPC failed ({status}): {message}")
        expected = struct.pack("<BBBH", RESPONSE_ID, 0, 1, self.request_id)
        if len(response) < 6 or response[:5] != expected:
            raise HardwareUxError("controller response identity/protocol mismatch")
        result = _json_object(response[6:])
        if response[5]:
            raise HardwareUxError(f"benchmark RPC failed ({response[5]}): {json.dumps(result)}")
        return result

    def hello(self) -> StrDict:
        self.verify_bridge()
        hello = self.rpc(0)
        if (
            hello.get("benchmark") is not True
            or hello.get("protocol") != 1
            or hello.get("ram_only") is not True
            or hello.get("requires_reboot") is not True
            or hello.get("max_events") != MAX_EVENTS
            or not isinstance(hello.get("build_id"), str)
            or not isinstance(hello.get("fixture"), str)
            or not isinstance(hello.get("fixture_version"), str)
            or not hello.get("build_id")
            or not hello.get("fixture")
            or not hello.get("fixture_version")
        ):
            raise HardwareUxError(
                "controller is not the compatible isolated hardware benchmark firmware"
            )
        return hello


def _count(summary: StrDict, key: str, maximum: int) -> int:
    value = summary.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= maximum:
        raise HardwareUxError(f"invalid result count: {key}")
    return value


def _validate_summary(summary: StrDict, script: HardwareScript, budget: int) -> None:
    count = _count(summary, "event_count", script.count)
    if (
        _count(summary, "uploaded_count", MAX_EVENTS) != script.count
        or _count(summary, "duration_us", MAX_DURATION_US) != script.duration_us
        or _count(summary, "memory_count", 64) != 1
        or not isinstance(summary.get("ok"), bool)
        or not isinstance(summary.get("failure"), str)
    ):
        raise HardwareUxError("summary does not match the uploaded program/result contract")
    metrics = _count(summary, "metric_count", 1024)
    lateness = _count(summary, "max_lateness_us", 0xFFFFFFFF)
    errors = [
        _count(summary, key, 0xFFFFFFFF)
        for key in (
            "foreign_requests",
            "physical_inputs",
            "midi_inputs",
            "notification_overflows",
            "lvgl_errors",
        )
    ]
    if summary["state"] == "completed" and (count != script.count or metrics == 0):
        raise HardwareUxError("completed run is missing events or metrics")
    if summary["ok"] and (
        summary["state"] != "completed" or summary["failure"] or any(errors) or lateness > budget
    ):
        raise HardwareUxError("benchmark success contradicts its state/error counters")


def _validate_timing(data: StrDict, count_key: str, total_key: str) -> int:
    count = _count(data, count_key, 0xFFFFFFFF)
    total = _count(data, total_key, 0xFFFFFFFFFFFFFFFF)
    maximum = _count(data, "max_us", 0xFFFFFFFF)
    if not maximum <= total <= count * maximum:
        raise HardwareUxError("inconsistent timing count/total/maximum")
    return count


def _validate_page(
    section: int,
    index: int,
    data: StrDict,
    script: HardwareScript,
    summary: StrDict,
    metric_names: set[str],
) -> None:
    if section in (1, 3) and _count(data, "index", MAX_EVENTS) != index:
        raise HardwareUxError("result page index does not match its request")
    if section == 1:
        due = _count(data, "due_us", MAX_DURATION_US)
        actual = _count(data, "actual_us", 0xFFFFFFFF)
        lateness = _count(data, "lateness_us", 0xFFFFFFFF)
        if (
            due != script.events[index]["due_us"]
            or actual - due != lateness
            or lateness > _count(summary, "max_lateness_us", 0xFFFFFFFF)
        ):
            raise HardwareUxError("event timing does not match the script/summary")
    elif section == 2:
        name = data.get("name")
        if not isinstance(name, str) or not name or name in metric_names:
            raise HardwareUxError("missing or duplicate metric name")
        count = _validate_timing(data, "count", "total_us")
        for key in ("max_at_us", "unit_a_max", "unit_b_max"):
            _count(data, key, 0xFFFFFFFF)
        bins = as_obj_list(data.get("bins_log2"))
        if bins is None or len(bins) != 33:
            raise HardwareUxError("invalid metric histogram length/count")
        bin_count = 0
        for value in bins:
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= 0xFFFFFFFF
            ):
                raise HardwareUxError("invalid metric histogram count")
            bin_count += value
        if bin_count != count:
            raise HardwareUxError("metric histogram does not sum to its sample count")
        metric_names.add(name)
    elif section == 3:
        _count(data, "frames", 0xFFFFFFFF)
        _count(data, "total_handler_us", 0xFFFFFFFFFFFFFFFF)
        if _count(data, "errors", 0xFFFFFFFF) != summary["lvgl_errors"]:
            raise HardwareUxError("LVGL errors do not match the summary")
        phases = as_obj_list(data.get("phases"))
        names = ("timer", "refresh", "layout", "style", "draw", "flush")
        if phases is None or len(phases) != len(names):
            raise HardwareUxError("incomplete LVGL phases")
        for phase, name in zip(phases, names, strict=True):
            values = as_str_dict(phase)
            if values is None or values.get("name") != name:
                raise HardwareUxError("unexpected LVGL phase name/order")
            _validate_timing(values, "calls", "total_us")
    elif section == 4:
        if data.get("phase") != "after_cleanup" or not isinstance(
            data.get("tracker_overflow"), bool
        ):
            raise HardwareUxError("invalid memory snapshot")
        for key in (
            "psram_user_bytes",
            "psram_free_bytes",
            "psram_largest_bytes",
            "allocation_failures",
            "lvgl_used_bytes",
            "lvgl_largest_bytes",
            "ram2_tail_bytes",
        ):
            _count(data, key, 0xFFFFFFFF)
        if summary["ok"] and data["tracker_overflow"]:
            raise HardwareUxError("benchmark success contradicts memory tracker overflow")


def run_hardware(
    script: HardwareScript,
    client: HardwareClient,
    output: Path,
    *,
    max_lateness_us: int = 100_000,
) -> StrDict:
    """Upload once, wait without polling, then retrieve bounded records; retain partial evidence."""
    hello = client.hello()
    if hello.get("state") != "idle":
        raise HardwareUxError("one run per boot: reboot the benchmark firmware before another run")
    if script.fixture is not None and script.fixture != hello.get("fixture"):
        raise HardwareUxError("scenario does not exactly match the firmware fixture")
    run_id = secrets.randbelow(0xFFFFFFFF) + 1
    upload = script.upload(run_id, max_lateness_us)
    output.mkdir(parents=True, exist_ok=False)
    manifest: StrDict = {
        "protocol": 1,
        "run_id": run_id,
        "script_sha256": script.sha256,
        "script_fnv1a": fnv1a(script.records),
        "duration_us": script.duration_us,
        "max_lateness_us": max_lateness_us,
        "bridge": client.bridge_info,
        "firmware": hello,
        "events": script.events,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    armed = False
    try:
        ack = client.rpc(1, upload)
        if (
            ack.get("run_id") != run_id
            or ack.get("script_fnv1a") != fnv1a(script.records)
            or ack.get("count") != script.count
        ):
            raise HardwareUxError("upload acknowledgement does not match the compiled script")
        armed = True  # A lost START acknowledgement can still mean the device started.
        client.rpc(2, struct.pack("<I", run_id))
        # Include permitted dispatch backlog before polling: an overlong final
        # frame must not make the host contaminate an otherwise valid run.
        time.sleep((script.duration_us + max_lateness_us) / 1_000_000 + 0.75)
        deadline = time.monotonic() + 5
        while client.rpc(3).get("state") in ("armed", "running", "finishing"):
            if time.monotonic() >= deadline:
                raise HardwareUxError("benchmark completion deadline exceeded")
            time.sleep(0.25)
        summary = client.rpc(4, struct.pack("<IBH", run_id, 0, 0))
        if summary.get("run_id") != run_id or summary.get("state") not in (
            "completed",
            "failed",
            "cancelled",
        ):
            raise HardwareUxError("benchmark did not reach a matching terminal state")
        armed = False
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        _validate_summary(summary, script, max_lateness_us)
        sections = (
            (1, "events", _count(summary, "event_count", MAX_EVENTS)),
            (2, "metrics", _count(summary, "metric_count", 1024)),
            (3, "lvgl", 3),
            (4, "memory", _count(summary, "memory_count", 64)),
        )
        metric_names: set[str] = set()
        last_actual_us = 0
        lvgl_totals: tuple[object, ...] | None = None
        with (output / "results.ndjson").open("x", encoding="utf-8") as trace:
            for section, name, count in sections:
                for index in range(count):
                    result = client.rpc(4, struct.pack("<IBH", run_id, section, index))
                    trace.write(
                        json.dumps({"section": name, "index": index, "data": result}) + "\n"
                    )
                    trace.flush()
                    _validate_page(section, index, result, script, summary, metric_names)
                    if section == 1:
                        actual = _count(result, "actual_us", 0xFFFFFFFF)
                        if actual < last_actual_us:
                            raise HardwareUxError("event dispatch timestamps are not monotonic")
                        last_actual_us = actual
                    if section == 3:
                        totals = tuple(
                            result[key] for key in ("frames", "total_handler_us", "errors")
                        )
                        if lvgl_totals is not None and totals != lvgl_totals:
                            raise HardwareUxError("LVGL aggregate changed between result pages")
                        lvgl_totals = totals
        if client.rpc(4, struct.pack("<IBH", run_id, 0, 0)) != summary:
            raise HardwareUxError("summary changed during result collection")
        completion: StrDict = {
            "collection_complete": True,
            "benchmark_ok": summary["ok"],
            "run_id": run_id,
        }
        (output / "completion.json").write_text(
            json.dumps(completion, indent=2) + "\n", encoding="utf-8"
        )
        return summary
    except (Exception, KeyboardInterrupt) as exc:
        error: StrDict = {"error": str(exc), "run_id": run_id}
        if armed:
            try:
                error["cancel"] = client.rpc(5, struct.pack("<I", run_id))
            except (OSError, ValueError) as cancel_error:
                error["cancel_error"] = str(cancel_error)
        (output / "error.json").write_text(json.dumps(error, indent=2) + "\n", encoding="utf-8")
        raise


def reboot_benchmark(client: HardwareClient, expected: StrDict) -> StrDict:
    """Reboot only positively identified benchmark firmware, then revalidate its identity."""
    current = client.hello()
    for key in ("build_id", "fixture", "fixture_version"):
        if current.get(key) != expected.get(key):
            raise HardwareUxError(f"benchmark {key} changed before reboot")
    client.rpc(6)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        time.sleep(0.5)
        try:
            ready = client.hello()
        except (OSError, ValueError):
            continue  # Bridge retains serial ownership and reconnects after the MCU restarts.
        for key in ("build_id", "fixture", "fixture_version"):
            if ready.get(key) != expected.get(key):
                raise HardwareUxError(f"benchmark {key} changed after reboot")
        if ready.get("state") == "idle":
            return ready
    raise HardwareUxError("benchmark did not return to idle after reboot; no upload attempted")


def run_repeated(
    script: HardwareScript,
    client: HardwareClient,
    output: Path,
    *,
    repeat: int = 1,
    fresh: bool = False,
    max_lateness_us: int = 100_000,
) -> tuple[StrDict, ...]:
    if not 1 <= repeat <= 100:
        raise HardwareUxError("repeat must be between 1 and 100")
    if output.exists():
        raise HardwareUxError("output directory already exists; choose a new directory")
    expected = client.hello()
    if script.fixture is not None and script.fixture != expected.get("fixture"):
        raise HardwareUxError("scenario does not exactly match the firmware fixture")
    if fresh:
        reboot_benchmark(client, expected)
    results: list[StrDict] = []
    for index in range(repeat):
        if index:
            reboot_benchmark(client, expected)
        # Recheck identity even when no reboot was requested, before the next upload.
        current = client.hello()
        if any(
            current.get(key) != expected.get(key)
            for key in ("build_id", "fixture", "fixture_version")
        ):
            raise HardwareUxError("benchmark identity changed between runs")
        destination = output if repeat == 1 else output / f"run-{index + 1:03d}"
        results.append(run_hardware(script, client, destination, max_lateness_us=max_lateness_us))
    return tuple(results)
