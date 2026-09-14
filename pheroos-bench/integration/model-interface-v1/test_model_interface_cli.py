"""Installed full negative instrument grid and real CLI abort contract."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pheroos_bench
from pheroos_bench import model_interface_v1_pilot as pilot

from test_model_interface_session import Instrument


BENCH = Path(__file__).resolve().parents[2]
PRIOR = BENCH / "next-cycle/coordination-repair-live-v1/campaign/actionability"


def metadata_model(tmp_path):
    model = tmp_path / "metadata-model"
    model.mkdir()
    source = BENCH / "integration/coordination-repair-v2/model-manifest-fixture.json"
    (model / "manifest.json").write_bytes(source.read_bytes())
    return model


def test_installed_complete_negative_grid_keeps_all_rows_and_never_admits_collaboration(tmp_path):
    model = Instrument("{}")
    report = pilot.collect(pilot.configuration(), tmp_path / "campaign", metadata_model(tmp_path), PRIOR,
                           authorized=True, instrument_model=model)
    assert report["cli"] == {"profile": "model_interface_cli_v1", "status": "COMPLETE", "exit_code": 0}
    assert report["instrument_only"] and report["status"] == "VALID_KNOWN"
    assert report["collaboration_admitted"] is False and len(model.requests) == 64
    assert all(g["episodes"] == 16 and g["objective_successes"] == g["public_accepted"] == 0 for g in report["groups"].values())
    root = tmp_path / "campaign"
    records = json.loads((root / "records.json").read_text())
    assert len(records) == 64 and all(r["instrument_only"] and r["status"] == "VALID_KNOWN" for r in records)
    combined = json.loads((root / "combined-accounting.json").read_text())
    assert combined["held_token_upper_bound"] == 65662 + 64 * 101
    assert combined["held_intent_slots"] == 114 + 64
    assert json.loads((root / "campaign-completion.json").read_text())["unstarted"] == []


def test_installed_module_retains_constructor_abort_and_nonzero_exit(tmp_path):
    site = Path(pheroos_bench.__file__).resolve().parents[1]
    assert site != BENCH / "src", "installed consumer required"
    external, output = tmp_path / "external", tmp_path / "campaign"
    external.mkdir()
    config = tmp_path / "config.json"
    config.write_text(json.dumps(pilot.configuration()))
    model = metadata_model(tmp_path)
    (external / "sitecustomize.py").write_text('''
import sys
class NoModelImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "transformers"}:
            raise AssertionError("No inference in installed CLI test")
sys.meta_path.insert(0, NoModelImports())
import pheroos_runtime.recorded_local_v3 as adapter
def fail(_path):
    raise RuntimeError("synthetic diagnostic loader failure")
adapter.RecordedLocalModelAdapter = fail
''')
    result = subprocess.run([sys.executable, "-m", "pheroos_bench.model_interface_v1_pilot",
        "--config", str(config), "--output", str(output), "--model-path", str(model),
        "--predecessor-root", str(PRIOR), "--authorized-diagnostic"], cwd=external,
        env={**os.environ, "PYTHONPATH": os.pathsep.join([str(external), str(site)])},
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 2, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "INVALID" and report["cli"]["status"] == "INVALID_ABORT"
    completion = json.loads((output / "campaign-completion.json").read_text())
    assert completion["executed"] == 0 and len(completion["unstarted"]) == completion["declared"] == 64
    assert all(r["cost"] is None and r["outcome"] is None for r in completion["unstarted"])
    combined = json.loads((output / "combined-accounting.json").read_text())
    assert combined["held_token_upper_bound"] == 65662 and combined["held_intent_slots"] == 114
    assert combined["current"]["allotments"] == []
