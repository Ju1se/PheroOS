"""Installed CLI process outcomes; retained fixtures are synthetic, never pilot data."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pheroos_bench
import pytest


CHILD = r'''
import json
from pathlib import Path
import sys

class NoModelImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "transformers"} or fullname.startswith("pheroos_runtime.recorded_local"):
            raise AssertionError("CLI fixtures must not load models: " + fullname)

sys.meta_path.insert(0, NoModelImports())
fixture_path, output, phase, installed_site = sys.argv[1:]
fixture = json.loads(Path(fixture_path).read_text())
from pheroos_bench import coordination_repair_v2_pilot as pilot
assert Path(pilot.__file__).resolve().is_relative_to(Path(installed_site).resolve())

def synthetic_collect(config, output, model_path, phase, predecessor_root, **kwargs):
    target = Path(output) / phase
    target.mkdir(parents=True)
    for name, value in fixture["retained"].items():
        (target / name).write_bytes(value.encode())
    return fixture["report"]

pilot.collect = synthetic_collect
sys.argv = ["coordination_repair_v2_pilot", "--config", fixture_path,
            "--output", output, "--phase", phase,
            "--model-path", "unused-model", "--predecessor-root", "unused-predecessor"]
raise SystemExit(pilot.main())
'''


@pytest.mark.parametrize("case,phase,code,status", [
    ("admitted", "actionability", 0, "COMPLETED"),
    ("not_admitted", "actionability", 3, "NOT_ADMITTED"),
    ("negative_result", "collaboration", 0, "COMPLETED"),
    ("no_eligible_prefixes", "collaboration", 0, "COMPLETED"),
    ("unmeasured_abort", "actionability", 2, "INVALID_ABORT"),
    ("invalid", "collaboration", 2, "INVALID_ABORT"),
    ("incomplete", "actionability", 2, "INVALID_ABORT"),
    ("unknown_accounting", "actionability", 2, "INVALID_ABORT"),
    ("unresolved_receipt", "collaboration", 2, "INVALID_ABORT"),
    ("missing_status_artifacts", "actionability", 2, "INVALID_ABORT"),
])
def test_installed_cli_exit_and_retained_records(tmp_path, case, phase, code, status):
    installed_site = Path(pheroos_bench.__file__).resolve().parents[1]
    source_root = Path(__file__).resolve().parents[2] / "src"
    assert installed_site != source_root, "This integration test requires the installed consumer"
    report = dict(counts_toward_verdict=False, fixture="synthetic CLI outcome")
    if phase == "actionability":
        report.update(measurement_status="COMPLETE", admitted=case != "not_admitted")
    else:
        report.update(status="VALID_KNOWN", comparisons={"success_difference": -1, "interval": None})
    completion = dict(status="COMPLETE", failure=None, unstarted=[], declared=1, executed=1)
    accounting = dict(known_tokens_complete=True, violation=None,
                      allotments=[dict(state="terminal", unknown_tokens=0)],
                      known_tokens=137, held_token_upper_bound=137)
    raw = [dict(status="VALID_KNOWN", success=False, outcome=0, cost=137, dollars=None)]
    if case == "no_eligible_prefixes":
        report.update(status="NO_ELIGIBLE_PREFIXES", comparisons={"success_difference": None, "interval": None})
    elif case == "unmeasured_abort":
        report.update(measurement_status="UNMEASURED", admitted=False)
        completion.update(status="INVALID_ABORT", failure={"stage": "synthetic_loader"}, executed=0,
                          unstarted=[dict(outcome=None, cost=None)])
        raw = []
    elif case == "invalid":
        report["status"] = "INVALID"
    elif case == "incomplete":
        completion.update(executed=0, unstarted=[dict(outcome=None, cost=None)])
    elif case == "unknown_accounting":
        accounting.update(known_tokens_complete=False, known_tokens=None, held_token_upper_bound=None)
    elif case == "unresolved_receipt":
        accounting["allotments"][0]["unknown_tokens"] = 64
        accounting["held_token_upper_bound"] = 201
    retained = {name: json.dumps(value, indent=2) + "\n" for name, value in {
        "records.json": raw, "campaign-completion.json": completion, "accounting.json": accounting,
    }.items()}
    if case == "missing_status_artifacts":
        retained = {"records.json": retained["records.json"]}
    fixture_path = tmp_path / "synthetic-fixture.json"
    fixture_path.write_text(json.dumps(dict(report=report, retained=retained)))
    external, output = tmp_path / "external", tmp_path / "cohort"
    external.mkdir()
    result = subprocess.run(
        [sys.executable, "-c", CHILD, str(fixture_path), str(output), phase, str(installed_site)],
        cwd=external, env={**os.environ, "PYTHONPATH": str(installed_site)},
        capture_output=True, text=True, timeout=15,
    )
    assert result.returncode == code, result.stderr + result.stdout
    assert result.stderr == ""
    observed = json.loads(result.stdout)
    assert observed.pop("cli") == dict(profile="coordination_repair_cli_v1", status=status, exit_code=code)
    assert observed == report
    phase_path = output / phase
    assert {p.name for p in phase_path.iterdir()} == set(retained)
    assert {name: (phase_path / name).read_bytes() for name in retained} == {
        name: value.encode() for name, value in retained.items()
    }
