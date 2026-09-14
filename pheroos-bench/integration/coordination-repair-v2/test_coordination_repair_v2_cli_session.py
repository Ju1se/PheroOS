"""Actual installed module entry point with a pre-inference constructor failure."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pheroos_bench
from pheroos_bench import coordination_repair_v2_pilot as pilot


def test_module_exit_retains_real_collection_abort_without_model_loading(tmp_path):
    installed_site = Path(pheroos_bench.__file__).resolve().parents[1]
    bench_root = Path(__file__).resolve().parents[2]
    assert installed_site != bench_root / "src", "This test requires the installed consumer"
    model, external, output = tmp_path / "metadata-only-model", tmp_path / "external", tmp_path / "cohort"
    model.mkdir()
    external.mkdir()
    manifest = Path(__file__).with_name("model-manifest-fixture.json")
    (model / "manifest.json").write_bytes(manifest.read_bytes())
    config = tmp_path / "config.json"
    config.write_text(json.dumps(pilot.configuration()))
    (external / "sitecustomize.py").write_text('''
import sys
from pathlib import Path

class NoModelImports:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"torch", "transformers"}:
            raise AssertionError("Synthetic CLI abort must not import model libraries")

sys.meta_path.insert(0, NoModelImports())
import pheroos_runtime.recorded_local_v2 as adapter
def fail_before_loading(_path):
    Path("synthetic-loader-called.txt").write_text("no model loaded or generated\\n")
    raise RuntimeError("synthetic CLI loader failure")
adapter.RecordedLocalModelAdapter = fail_before_loading
''')
    result = subprocess.run(
        [sys.executable, "-m", "pheroos_bench.coordination_repair_v2_pilot",
         "--config", str(config), "--output", str(output), "--model-path", str(model),
         "--phase", "actionability", "--predecessor-root", str(bench_root / "next-cycle/coordination-repair-v1"),
         "--authorized-additional-campaign"],
        cwd=external, env={**os.environ, "PYTHONPATH": os.pathsep.join([str(external), str(installed_site)])},
        capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["measurement_status"] == "UNMEASURED" and report["admitted"] is False
    assert report["cli"] == dict(profile="coordination_repair_cli_v1", status="INVALID_ABORT", exit_code=2)
    phase = output / "actionability"
    completion = json.loads((phase / "campaign-completion.json").read_text())
    assert completion["status"] == "INVALID_ABORT" and completion["executed"] == 0
    assert completion["declared"] == len(completion["unstarted"]) == 28
    assert all(row["outcome"] is None and row["cost"] is None for row in completion["unstarted"])
    assert completion["failure"]["message"] == "synthetic CLI loader failure"
    assert json.loads((phase / "records.json").read_text()) == []
    accounting = json.loads((phase / "accounting.json").read_text())
    assert accounting["allotments"] == [] and accounting["held_token_upper_bound"] == 0
    combined = json.loads((phase / "combined-accounting.json").read_text())
    assert combined["held_intent_slots"] == combined["predecessor"]["retained_intent_slots"] == 1
    assert combined["predecessor"]["observed_model_dispatches"] == 0
    assert (external / "synthetic-loader-called.txt").read_text() == "no model loaded or generated\n"
