from __future__ import annotations

import json
import re
import struct
from io import BytesIO
from pathlib import Path

import pytest

from ms.core.structured import StrDict
from ms.services import ux_hardware as hw


def no_wait(_: float) -> None:
    pass


def script(tmp_path: Path, text: str) -> hw.HardwareScript:
    path = tmp_path / "input.ux"
    path.write_text(text, encoding="utf-8")
    return hw.compile_script(path)


def hello() -> StrDict:
    return {
        "benchmark": True,
        "protocol": 1,
        "build_id": "source-123",
        "fixture": "bench-macro-v1",
        "fixture_version": "bench-macro-v1",
        "max_events": 2048,
        "state": "idle",
        "run_id": 0,
        "ram_only": True,
        "requires_reboot": True,
    }


def test_compile_native_subset_stable_ties_and_exact_wire(tmp_path: Path) -> None:
    compiled = script(
        tmp_path,
        """
# comment
0 scenario bench-macro-v1
30 encoder_value MACRO_1 0.123
10 tap NAV 20
30 capture screen result // semantic marker, not a screenshot
30 assert_view MACRO
30 assert_mode macro
40 transport start
100 wait
""",
    )
    assert compiled.fixture == "bench-macro-v1"
    assert compiled.duration_us == 1_100_000
    assert len(compiled.sha256) == 64
    assert [event["kind"] for event in compiled.events] == [1, 2, 1, 3, 4, 5, 6]
    assert hw.RECORD.unpack(compiled.records[:12]) == (10000, 1, 0, 40, 1)
    assert hw.RECORD.unpack(compiled.records[12:24]) == (30000, 2, 0, 301, 123)
    assert compiled.events[3]["label"] == "result"
    assert compiled.upload(42, 1000)[:14] == struct.pack("<IHII", 42, 7, 1_100_000, 1000)
    assert hw.fnv1a(b"hello") == 0x4F9F2CAB


@pytest.mark.parametrize(
    "text",
    [
        "0 encoder NAV 1",
        "0 unknown hello",
        "0 capture banana screenshot",
        "0 encoder_value OPT nan",
        "0 encoder_value OPT 0.0001",
        "0 encoder_value OPT 2147483.648",
        "0 encoder_value UNKNOWN 0.1",
        "0 tap NAV 0",
        "0 button NAV up",
        "0 button NAV down",
        "0 tap NAV\n5 tap NAV",
        "0 tap NAV extra garbage",
        "0 wait extra",
        "1 scenario bench-macro-v1",
        "0 scenario a\n0 scenario b\n0 marker x",
        "120001 marker too_late",
        "-1 marker negative",
        "0 assert_view MISSING",
        "0 transport record",
        "0 scenario bench-macro-v1",
        "0 marker x extra",
    ],
)
def test_compile_rejects_unsupported_or_ambiguous_input(tmp_path: Path, text: str) -> None:
    with pytest.raises(hw.HardwareUxError):
        script(tmp_path, text)


def test_compile_size_duration_and_unsigned_assert_hash(tmp_path: Path) -> None:
    with pytest.raises(hw.HardwareUxError, match="2048"):
        script(tmp_path, "0 marker x\n" * 2049)
    path = tmp_path / "bounds.ux"
    path.write_text("120000 marker x\n", encoding="utf-8")
    assert hw.compile_script(path, duration_ms=120000).duration_us == 120000000
    with pytest.raises(hw.HardwareUxError, match="duration"):
        hw.compile_script(path, duration_ms=119999)
    compiled = script(tmp_path, "0 assert_mode abc\n")
    assert hw.RECORD.unpack(compiled.records)[4] & 0xFFFFFFFF == hw.fnv1a(b"abc")


def test_foreground_blocks_are_explicit_bounded_and_nonoverlapping(tmp_path: Path) -> None:
    compiled = script(
        tmp_path, "0 block_foreground 100\n100 block_foreground 250\n350 block_foreground 1000"
    )
    assert compiled.duration_us == 2_350_000
    assert [event[4] for event in hw.RECORD.iter_unpack(compiled.records)] == [
        100000, 250000, 1000000
    ]
    for text in ("0 block_foreground 0", "0 block_foreground 1001",
                 "0 block_foreground -1", "0 block_foreground 100\n99 marker overlap",
                 "120000 block_foreground 1"):
        with pytest.raises(hw.HardwareUxError):
            script(tmp_path, text)


class FakeClient(hw.HardwareClient):
    def __init__(self) -> None:
        super().__init__(8001, "18040250")
        self.identity = hello()
        self.calls: list[int] = []
        self.run_id = 0
        self.count = 0
        self.duration_us = 0
        self.due_times: list[int] = []
        self.bad_ack = False
        self.summary_changes: StrDict = {}
        self.page_changes: dict[tuple[int, int], StrDict] = {}
        self.fail_page: tuple[int, int] | None = None
        self.summary_reads = 0
        self.change_summary = False

    def hello(self) -> StrDict:
        return dict(self.identity)

    def rpc(self, operation: int, body: bytes = b"") -> StrDict:
        self.calls.append(operation)
        if operation == 1:
            self.run_id, self.count, self.duration_us, _ = struct.unpack("<IHII", body[:14])
            self.due_times = [row[0] for row in hw.RECORD.iter_unpack(body[14:])]
            self.summary_reads = 0
            return {
                "run_id": self.run_id,
                "count": self.count,
                "script_fnv1a": 0 if self.bad_ack else hw.fnv1a(body[14:]),
            }
        if operation == 3:
            return {"state": "completed", "run_id": self.run_id}
        if operation == 4:
            run_id, section, index = struct.unpack("<IBH", body)
            assert run_id == self.run_id
            if (section, index) == self.fail_page:
                raise OSError("simulated result connection loss")
            if section == 0:
                self.summary_reads += 1
                return {
                    "state": "completed",
                    "run_id": self.run_id,
                    "ok": True,
                    "failure": "",
                    "event_count": self.count,
                    "uploaded_count": self.count,
                    "metric_count": 1,
                    "memory_count": 1,
                    "duration_us": self.duration_us,
                    "max_lateness_us": 0,
                    "foreign_requests": 0,
                    "physical_inputs": 0,
                    "midi_inputs": 0,
                    "notification_overflows": int(self.change_summary and self.summary_reads > 1),
                    "lvgl_errors": 0,
                    **self.summary_changes,
                }
            if (section, index) in self.page_changes:
                return self.page_changes[(section, index)]
            if section == 1:
                return {
                    "index": index,
                    "due_us": self.due_times[index],
                    "actual_us": self.due_times[index],
                    "lateness_us": 0,
                }
            if section == 2:
                return {
                    "name": "main.loop",
                    "count": 1,
                    "total_us": 12,
                    "max_us": 12,
                    "max_at_us": 12,
                    "unit_a_max": 0,
                    "unit_b_max": 0,
                    "bins_log2": [0, 0, 0, 0, 1] + [0] * 28,
                }
            if section == 3:
                return {
                    "index": index,
                    "frames": 1,
                    "total_handler_us": 12,
                    "errors": 0,
                    "phases": [
                        {"name": name, "calls": 1, "total_us": 2, "max_us": 2}
                        for name in ("timer", "refresh", "layout", "style", "draw", "flush")
                    ],
                }
            return {
                "phase": "after_cleanup",
                "tracker_overflow": False,
                **dict.fromkeys(
                    (
                        "psram_user_bytes",
                        "psram_free_bytes",
                        "psram_largest_bytes",
                        "allocation_failures",
                        "lvgl_used_bytes",
                        "lvgl_largest_bytes",
                        "ram2_tail_bytes",
                    ),
                    0,
                ),
            }
        return {"ok": True}


def test_run_waits_without_polling_and_keeps_manifest_and_results(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    compiled = script(tmp_path, "0 marker first\n")
    waits: list[float] = []

    def wait(seconds: float) -> None:
        assert client.calls == [1, 2]
        waits.append(seconds)

    monkeypatch.setattr(hw.time, "sleep", wait)
    output = tmp_path / "results"
    result = hw.run_hardware(compiled, client, output)
    assert result["ok"] is True
    assert waits == [1.85]
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["script_sha256"] == compiled.sha256
    assert manifest["firmware"]["build_id"] == "source-123"
    assert len((output / "results.ndjson").read_text().splitlines()) == 6
    assert json.loads((output / "completion.json").read_text()) == {
        "collection_complete": True,
        "benchmark_ok": True,
        "run_id": client.run_id,
    }
    assert 5 not in client.calls
    with pytest.raises(FileExistsError):
        hw.run_hardware(compiled, client, output)


def test_bad_upload_ack_never_starts(tmp_path: Path) -> None:
    client = FakeClient()
    client.bad_ack = True
    compiled = script(tmp_path, "0 marker x")
    output = tmp_path / "bad"
    with pytest.raises(hw.HardwareUxError, match="acknowledgement"):
        hw.run_hardware(compiled, client, output)
    assert client.calls == [1]
    assert (output / "error.json").is_file()
    assert not (output / "completion.json").exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"event_count": 0},
        {"event_count": 2},
        {"uploaded_count": 2},
        {"duration_us": 1},
        {"memory_count": 0},
        {"metric_count": 0},
        {"event_count": "1"},
        {"memory_count": True},
        {"ok": "true"},
        {"state": "failed"},
        {"failure": "unexpected_failure"},
        {"foreign_requests": 1},
        {"physical_inputs": 1},
        {"midi_inputs": 1},
        {"max_lateness_us": 100001},
    ],
)
def test_inconsistent_summary_never_certifies_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changes: StrDict,
) -> None:
    monkeypatch.setattr(hw.time, "sleep", no_wait)
    client = FakeClient()
    client.summary_changes = changes
    output = tmp_path / "invalid-summary"
    with pytest.raises(hw.HardwareUxError):
        hw.run_hardware(script(tmp_path, "0 marker x"), client, output)
    assert (output / "error.json").is_file()
    assert not (output / "completion.json").exists()


@pytest.mark.parametrize(
    "section,index,changes",
    [
        (1, 0, {}),
        (1, 0, {"index": 1}),
        (1, 0, {"due_us": 1}),
        (1, 0, {"actual_us": 1}),
        (1, 0, {"lateness_us": -1}),
        (2, 0, {"bins_log2": [1] * 32}),
        (2, 0, {"bins_log2": [0] * 33}),
        (2, 0, {"bins_log2": [True] + [0] * 32}),
        (2, 0, {"total_us": "12"}),
        (2, 0, {"total_us": 13}),
        (2, 0, {"name": ""}),
        (3, 1, {"index": 0}),
        (3, 1, {"frames": 2}),
        (3, 1, {"errors": 1}),
        (3, 1, {"phases": []}),
        (4, 0, {"phase": "during_run"}),
        (4, 0, {"tracker_overflow": True}),
    ],
)
def test_inconsistent_page_retains_evidence_without_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    section: int,
    index: int,
    changes: StrDict,
) -> None:
    monkeypatch.setattr(hw.time, "sleep", no_wait)
    client = FakeClient()
    original = client.rpc

    def corrupt(operation: int, body: bytes = b"") -> StrDict:
        result = original(operation, body)
        if operation == 4 and struct.unpack("<IBH", body)[1:] == (section, index):
            return {**result, **changes} if changes else {}
        return result

    monkeypatch.setattr(client, "rpc", corrupt)
    output = tmp_path / "invalid-page"
    with pytest.raises(hw.HardwareUxError):
        hw.run_hardware(script(tmp_path, "0 marker x"), client, output)
    assert (output / "results.ndjson").read_text().strip()
    assert (output / "error.json").is_file()
    assert not (output / "completion.json").exists()


@pytest.mark.parametrize("changed_summary", [False, True])
def test_result_loss_or_summary_mutation_aborts_repeat_without_certificate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    changed_summary: bool,
) -> None:
    monkeypatch.setattr(hw.time, "sleep", no_wait)
    client = FakeClient()
    client.change_summary = changed_summary
    client.fail_page = None if changed_summary else (3, 1)
    output = tmp_path / "partial"
    with pytest.raises((OSError, hw.HardwareUxError)):
        hw.run_repeated(script(tmp_path, "0 marker x"), client, output, repeat=2)
    trial = output / "run-001"
    assert json.loads((trial / "summary.json").read_text())["ok"] is True
    assert (trial / "error.json").is_file()
    assert not (trial / "completion.json").exists()
    assert not (output / "run-002").exists()
    assert 6 not in client.calls


def test_duplicate_metric_names_and_nonmonotonic_events_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hw.time, "sleep", no_wait)
    client = FakeClient()
    client.summary_changes = {"metric_count": 2}
    with pytest.raises(hw.HardwareUxError, match="duplicate"):
        hw.run_hardware(script(tmp_path, "0 marker x"), client, tmp_path / "duplicate")
    client = FakeClient()
    client.summary_changes = {"max_lateness_us": 200000}
    client.page_changes[(1, 0)] = {
        "index": 0,
        "due_us": 0,
        "actual_us": 200000,
        "lateness_us": 200000,
    }
    with pytest.raises(hw.HardwareUxError, match="monotonic"):
        hw.run_hardware(
            script(tmp_path, "0 marker x\n100 marker y"),
            client,
            tmp_path / "reordered",
            max_lateness_us=1000000,
        )


def test_failed_benchmarks_still_collect_complete_reports_for_each_requested_trial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(hw.time, "sleep", no_wait)
    client = FakeClient()
    client.summary_changes = {
        "state": "failed",
        "ok": False,
        "failure": "physical_input_contamination",
        "event_count": 0,
        "metric_count": 0,
    }
    output = tmp_path / "failed-trials"
    results = hw.run_repeated(script(tmp_path, "0 marker x"), client, output, repeat=2)
    assert all(result["ok"] is False for result in results)
    assert client.calls.count(6) == 1
    for trial in (output / "run-001", output / "run-002"):
        completion = json.loads((trial / "completion.json").read_text())
        assert completion["collection_complete"] is True
        assert completion["benchmark_ok"] is False
        assert not (trial / "error.json").exists()


def test_interrupt_requests_cancel_and_retains_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt(_: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(hw.time, "sleep", interrupt)
    client = FakeClient()
    output = tmp_path / "cancelled"
    with pytest.raises(KeyboardInterrupt):
        hw.run_hardware(script(tmp_path, "0 marker x"), client, output)
    assert client.calls == [1, 2, 5]
    assert (output / "error.json").is_file()


def test_fixture_or_used_boot_fails_before_upload(tmp_path: Path) -> None:
    client = FakeClient()
    with pytest.raises(hw.HardwareUxError, match="scenario"):
        hw.run_hardware(script(tmp_path, "0 scenario other\n0 marker x"), client, tmp_path / "out")
    client.identity["state"] = "completed"
    with pytest.raises(hw.HardwareUxError, match="one run per boot"):
        hw.run_hardware(script(tmp_path, "0 marker x"), client, tmp_path / "out")
    assert client.calls == []


def test_repeat_reboots_only_between_trials_and_rechecks_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_wait(_: float) -> None:
        pass

    monkeypatch.setattr(hw.time, "sleep", no_wait)
    client = FakeClient()
    results = hw.run_repeated(script(tmp_path, "0 marker x"), client, tmp_path / "repeat", repeat=2)
    assert len(results) == 2
    assert client.calls.count(6) == 1
    assert client.calls.index(6) > client.calls.index(4)
    assert (tmp_path / "repeat/run-002/manifest.json").is_file()
    expected = hello()
    client.identity["build_id"] = "changed"
    before = list(client.calls)
    with pytest.raises(hw.HardwareUxError, match="before reboot"):
        hw.reboot_benchmark(client, expected)
    assert client.calls == before


class FakeSocket:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.sent = b""

    def __enter__(self) -> FakeSocket:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent += data

    def recv(self, count: int) -> bytes:
        chunk = self.data[: min(count, 3)]  # Exercise fragmented TCP reads.
        self.data = self.data[len(chunk) :]
        return chunk

    def makefile(self, mode: str) -> BytesIO:
        assert mode == "rb"
        return BytesIO(self.data)


def test_bridge_binary_envelope_and_response_correlation(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = struct.pack("<BBBHB", 0xDF, 0, 1, 43, 0) + b'{"ok":true}'
    frame = struct.pack("<4sBBHIHH", b"OCRS", 1, 0, 43, len(payload), 0, 0) + payload
    stream = FakeSocket(frame)

    def connect(*args: object, **kwargs: object) -> FakeSocket:
        return stream

    monkeypatch.setattr(hw.socket, "create_connection", connect)
    client = hw.HardwareClient(8001, "18040250")
    client.request_id = 42
    assert client.rpc(3) == {"ok": True}
    assert stream.sent[:16] == struct.pack("<4sBBHII", b"OCRQ", 1, 0xDF, 43, 3000, 6)
    assert stream.sent[16:] == struct.pack("<BBBHB", 0xDE, 0, 1, 43, 3)
    client.request_id = 43
    stream.data = frame
    with pytest.raises(hw.HardwareUxError, match="invalid"):
        client.rpc(3)


def test_normal_firmware_is_never_rebooted(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(_: hw.HardwareClient) -> StrDict:
        return {}

    monkeypatch.setattr(hw.HardwareClient, "verify_bridge", verify)
    calls: list[int] = []

    def normal(_: hw.HardwareClient, operation: int, body: bytes = b"") -> StrDict:
        del body
        calls.append(operation)
        return {"protocol": 1, "state": "idle"}

    monkeypatch.setattr(hw.HardwareClient, "rpc", normal)
    with pytest.raises(hw.HardwareUxError, match="isolated"):
        hw.reboot_benchmark(hw.HardwareClient(8001, "18040250"), hello())
    assert calls == [0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("controller_serial", "other-controller"),
        ("control_port", 8000),
        ("paused", True),
        ("serial_open", False),
        ("ok", False),
        ("instance_id", None),
    ],
)
def test_bridge_identity_refusal_is_read_only(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    info: StrDict = {
        "ok": True,
        "paused": False,
        "serial_open": True,
        "controller_serial": "18040250",
        "control_port": 8001,
        "instance_id": "bitwig-hardware-18040250",
    }
    info[field] = value
    stream = FakeSocket(json.dumps(info).encode("utf-8") + b"\n")

    def connect(*args: object, **kwargs: object) -> FakeSocket:
        return stream

    monkeypatch.setattr(hw.socket, "create_connection", connect)
    with pytest.raises(hw.HardwareUxError, match="identity"):
        hw.HardwareClient(8001, "18040250").hello()
    assert stream.sent == b'{"schema":1,"cmd":"info"}\n'


@pytest.mark.parametrize(
    "frame",
    [
        b"OCRS",  # Truncated header.
        struct.pack("<4sBBHIHH", b"OCRS", 1, 0, 43, 32769, 0, 0),
        struct.pack("<4sBBHIHH", b"OCRS", 1, 4, 43, 0, 0, 0),
        struct.pack("<4sBBHIHH", b"OCRS", 1, 0, 43, 6, 0, 0) + b"\xdf\x00\x01\x2c\x00\x00",
    ],
)
def test_malformed_or_failed_bridge_response_is_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
    frame: bytes,
) -> None:
    stream = FakeSocket(frame)

    def connect(*args: object, **kwargs: object) -> FakeSocket:
        return stream

    monkeypatch.setattr(hw.socket, "create_connection", connect)
    client = hw.HardwareClient(8001, "18040250")
    client.request_id = 42
    with pytest.raises(hw.HardwareUxError):
        client.rpc(3)


def test_workspace_input_ids_and_reserved_protocol_ids_still_match() -> None:
    workspace = Path(__file__).resolve().parents[3]
    header = workspace / "midi-studio/device-support/src/ms/device_support/v1/InputIds.hpp"
    protocol = workspace / "midi-studio/plugin-bitwig/src/protocol/MessageID.hpp"
    if not header.is_file() or not protocol.is_file():
        pytest.skip("optional Core/Bitwig checkouts are not present")
    text = header.read_text(encoding="utf-8")
    for enum_name, expected in (("ButtonID", hw.BUTTONS), ("EncoderID", hw.ENCODERS)):
        block = re.search(rf"enum class {enum_name}[^{{]*\{{([^}}]+)\}}", text)
        assert block is not None
        actual = {name: int(value) for name, value in re.findall(r"(\w+)\s*=\s*(\d+)", block[1])}
        assert actual == expected
    ids = [
        int(value, 16)
        for value in re.findall(r"=\s*0x([0-9a-fA-F]+)", protocol.read_text(encoding="utf-8"))
    ]
    assert ids and max(ids) < hw.REQUEST_ID, "Bitwig generator entered the reserved Core RPC range"


def test_versioned_benchmark_scripts_compile_with_target_assertions() -> None:
    folder = Path(__file__).resolve().parents[3] / "midi-studio/core/script/bench"
    if not folder.is_dir():
        pytest.skip("optional Core checkout is not present")
    expected = {
        "idle-playback.ux": (11, 10_000_000, 0xE954535B),
        "macro-edit.ux": (67, 20_000_000, 0x52D2F5BB),
        "modulator-transitions.ux": (108, 20_000_000, 0x22E86618),
    }
    for name, (count, duration, checksum) in expected.items():
        compiled = hw.compile_script(folder / name)
        assert compiled.fixture == "bench-macro-v1"
        assert compiled.count == count
        assert compiled.duration_us == duration
        assert hw.fnv1a(compiled.records) == checksum
        kinds = {event["kind"] for event in compiled.events}
        assert {3, 4, 5, 6} <= kinds  # Every workload has markers, mode/view assertions, transport.
