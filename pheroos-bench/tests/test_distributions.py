from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
CONFIGS = ("experiment.json", "experiment-e2.json")


def _run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_packaged_configs_equal_frozen_sources() -> None:
    for name in CONFIGS:
        assert (ROOT / "src" / "pheroos_bench" / "data" / name).read_bytes() == (
            ROOT / name
        ).read_bytes()


@pytest.fixture(scope="module")
def distributions(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    source = tmp_path_factory.mktemp("bench-build-source")
    shutil.copytree(
        ROOT / "src",
        source / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    shutil.copy2(ROOT / "pyproject.toml", source / "pyproject.toml")
    output = tmp_path_factory.mktemp("bench-distributions")
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--wheel",
            "--sdist",
            "--outdir",
            str(output),
        ],
        source,
    )
    return {"wheel": next(output.glob("*.whl")), "sdist": next(output.glob("*.tar.gz"))}


@pytest.mark.parametrize("kind", ("wheel", "sdist"))
def test_installed_configs_and_fingerprint_outside_source(
    kind: str, distributions: dict[str, Path], tmp_path: Path
) -> None:
    target = tmp_path / "installed"
    _run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            "--ignore-installed",
            "--target",
            str(target),
            str(distributions[kind]),
        ],
        tmp_path,
    )
    # -S plus an explicit target means no editable source package can rescue
    # the installed configuration loaders. This check does not run an experiment.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(target)
    output = _run(
        [
            sys.executable,
            "-S",
            "-c",
            """
import hashlib, json
from pathlib import Path
from pheroos_bench.config import CONFIG_PATH as e1_path, load_config
from pheroos_bench.e2_config import CONFIG_PATH as e2_path, load_e2_config
assert load_config().steps == 500
assert load_e2_config().route_count == 128
print(json.dumps({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (e1_path, e2_path)}))
""",
        ],
        tmp_path,
        env,
    )
    assert json.loads(output) == {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in CONFIGS
    }

    # e2_run imports NumPy. Reuse only that declared dependency's site-packages;
    # pin the bench import location to the just-installed artifact above.
    import numpy

    env["PYTHONPATH"] = os.pathsep.join(
        (str(target), str(Path(numpy.__file__).resolve().parents[1]))
    )
    output = _run(
        [
            sys.executable,
            "-S",
            "-c",
            """
import json
from pathlib import Path
from pheroos_bench import e2_run
print(json.dumps([str(Path(e2_run.__file__).resolve()), e2_run._code_fingerprint()]))
""",
        ],
        tmp_path,
        env,
    )
    module_path, fingerprint = json.loads(output)
    assert target.resolve() in Path(module_path).parents
    digest = hashlib.sha256()
    for path in sorted((ROOT / "src" / "pheroos_bench").glob("e2_*.py")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    assert fingerprint == digest.hexdigest()
    assert fingerprint != hashlib.sha256(b"").hexdigest()

    # Exercise the new CLI from the artifact, without site/editable fallback,
    # credentials, or model calls. This catches missing installed E3 modules.
    env["PYTHONPATH"] = str(target)
    output = _run(
        [
            sys.executable,
            "-S",
            "-c",
            """
import json
from pathlib import Path
from pheroos_bench import e3_llm, e3_verdict
assert e3_verdict.ESTIMAND == "paired_item_mean_v1"
def no_calls(**kwargs):
    raise AssertionError("dry-run must never call a provider")
e3_llm._post_json = no_calls
items = Path("preview-items.jsonl")
items.write_text(json.dumps({"question": "1+1?", "answer": "2"}) + "\\n")
assert e3_llm.main([
    "--items", str(items), "--dry-run", "--n", "4",
    "--repetitions", "3", "--api-key-env", ""
]) == 0
""",
        ],
        tmp_path,
        env,
    )
    preview = json.loads(output)
    assert preview["dry_run"] is True
    assert preview["call_count"] == 12
    assert preview["monetary_upper_bound"] is None
