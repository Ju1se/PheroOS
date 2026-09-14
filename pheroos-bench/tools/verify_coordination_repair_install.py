"""Build/install the experimental consumer with exact retained runtime/core wheels.

Uses the caller's existing pytest/numpy/build tooling, installs no dependencies,
and executes from a fresh external directory with no source import path.
"""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def run(args, cwd, env=None):
    result = subprocess.run(args, cwd=cwd, env=env, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site", type=Path)
    parser.add_argument("--retain-wheel", type=Path)
    parser.add_argument("--runtime-cohort", choices=("dev2", "dev3"), default="dev2")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "next-cycle/coordination-repair-v1/artifacts"
    input_file = "installation-inputs.json" if args.runtime_cohort == "dev2" else "installation-inputs-dev3.json"
    inputs = json.loads((artifacts / input_file).read_text())
    for name, expected in inputs.items():
        if sha256((artifacts/name).read_bytes()).hexdigest() != expected:
            raise ValueError("retained installation artifact identity mismatch: " + name)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="pheroos-repair-installed-") as directory:
        staging = Path(directory)
        build = staging / "build"
        run([sys.executable,"-m","build","--no-isolation","--wheel","--outdir",str(build)],root)
        wheel, = build.glob("*.whl")
        site = args.site.resolve() if args.site else staging / "site"
        if site.exists():
            raise FileExistsError("installation site must be fresh")
        external = staging / "external"
        external.mkdir()
        run([sys.executable,"-m","pip","install","--no-deps","--no-build-isolation",
             "--ignore-installed","--target",str(site),str(wheel),
             *[str(artifacts/name) for name in inputs]],external)
        env = {**os.environ, "PYTHONPATH":str(site), "PYTEST_DISABLE_PLUGIN_AUTOLOAD":"1"}
        identities = json.loads(run([sys.executable,"-c",
            "import json,pheroos,pheroos_runtime,pheroos_bench,importlib.metadata as m; "
            "print(json.dumps({'paths':[pheroos.__file__,pheroos_runtime.__file__,pheroos_bench.__file__],"
            "'versions':{n:m.version(n) for n in ['pheroos','pheroos-runtime','pheroos-bench']}}))"],external,env))
        if any(not Path(p).is_relative_to(site) for p in identities["paths"]):
            raise RuntimeError("source checkout leaked into installed consumer")
        if identities["versions"]["pheroos-runtime"] != "0.1.0." + args.runtime_cohort or identities["versions"]["pheroos-bench"] != "0.1.1.dev2":
            raise RuntimeError("experimental cohort identity mismatch")
        config = staging / "pytest.ini"
        config.write_text("[pytest]\n")
        tests = run([sys.executable,"-m","pytest","-q","-rs","-c",str(config),
                     str(root/"integration/coordination-repair-v1"),
                     str(root/"tests/test_coordination_repair_v1_tasks.py"),
                     str(root/"tests/test_coordination_repair_v1_measurement.py"),
                     str(root/"tests/test_coordination_repair_v1_pilot.py")],external,env)
        if "skipped" in tests:
            raise RuntimeError("missing integration coverage cannot count as a pass: " + tests)
        if args.retain_wheel:
            args.retain_wheel.mkdir(parents=True,exist_ok=True)
            saved = args.retain_wheel / wheel.name
            with saved.open("xb") as stream:
                stream.write(wheel.read_bytes())
        result = {"schema":"coordination_repair_installed_consumer_v1","status":"PASS",
                  "identities":identities,"inputs":inputs,"bench_wheel":wheel.name,
                  "bench_wheel_sha256":sha256(wheel.read_bytes()).hexdigest(),
                  "test_output":tests,"elapsed_seconds":time.monotonic()-started,
                  "source_independent":True,"network_calls":0,"model_calls":0}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(result,stream,indent=2)
            stream.write("\n")
        print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
