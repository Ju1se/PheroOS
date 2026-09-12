import json

import pytest

from pheroos_bench import r0_measurement, r0_self_check


def test_numerically_unrepresentable_cost_produces_diagnostic():
    config, rows = r0_self_check.fixture([(0, 0), (1, 1)])
    rows[0]["cost"] = 10**400
    report = r0_measurement.analyze(rows, config)
    assert report["status"] == "INVALID_ABORT"
    assert report["reason"].startswith("unrepresentable_measurement")


def test_cli_saves_invalid_diagnostic_and_exits_nonzero(tmp_path):
    config, rows = r0_self_check.fixture([(0, 0), (1, 1)])
    config_path = tmp_path / "config.json"
    records = tmp_path / "records.ndjson"
    output = tmp_path / "report.json"
    config_path.write_text(json.dumps(config))
    records.write_text("\n".join(json.dumps(row) for row in rows[:-1]))
    args = [
        "--config",
        str(config_path),
        "--records",
        str(records),
        "--output",
        str(output),
    ]
    assert r0_measurement.main(args) == 2
    report = json.loads(output.read_text())
    assert report["status"] == "INVALID_ABORT"
    assert report["reason"] == "incomplete_episode_grid"
    original = output.read_bytes()
    with pytest.raises(FileExistsError):
        r0_measurement.main(args)
    assert output.read_bytes() == original


def test_duplicate_json_keys_are_not_silently_overwritten(tmp_path):
    config_path, records, output = (
        tmp_path / name for name in ("config.json", "rows.jsonl", "out.json")
    )
    config_path.write_text('{"phase":"confirmatory","phase":"instrument_check"}')
    records.write_text("")
    assert (
        r0_measurement.main(
            [
                "--config",
                str(config_path),
                "--records",
                str(records),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert json.loads(output.read_text())["reason"].startswith("duplicate_json_key")


def test_self_check_bad_runtime_json_saves_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        r0_self_check, "self_check", lambda: {"status": "R0_INSTRUMENT_CHECKS_PASSED"}
    )
    snapshot, output = tmp_path / "snapshot.json", tmp_path / "report.json"
    snapshot.write_text('{"run": {}, "run": {}}')
    assert (
        r0_self_check.main(
            ["--output", str(output), "--runtime-snapshot", str(snapshot)]
        )
        == 2
    )
    report = json.loads(output.read_text())
    assert report["status"] == "R0_INSTRUMENT_CHECKS_FAILED"
    assert (
        report["runtime_snapshots"][0]["reconciliation"]["validation_status"]
        == "INVALID_ABORT"
    )
