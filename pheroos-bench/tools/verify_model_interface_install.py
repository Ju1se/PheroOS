"""Install exact local diagnostic artifacts and run mandatory offline consumers."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def run(argv, cwd, env=None):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site", type=Path)
    parser.add_argument("--retain-wheel", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    inputs_path = root / "next-cycle/model-interface-v1/installation-inputs.json"
    inputs = json.loads(inputs_path.read_text())
    for item in inputs:
        path = root / item["path"]
        if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("installation artifact mismatch: " + item["path"])
    with tempfile.TemporaryDirectory(prefix="pheroos-interface-installed-") as directory:
        scratch = Path(directory)
        build, external = scratch / "build", scratch / "external"
        external.mkdir()
        run([sys.executable, "-m", "build", "--no-isolation", "--wheel", "--outdir", str(build)], root)
        wheel, = build.glob("*.whl")
        site = args.site.resolve() if args.site else scratch / "site"
        if site.exists():
            raise FileExistsError("fresh installation site required")
        run([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", "--ignore-installed",
             "--target", str(site), str(wheel), *[str(root / i["path"]) for i in inputs]], external)
        env = {**os.environ, "PYTHONPATH": str(site), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
        identities = json.loads(run([sys.executable, "-c",
            "import json,pheroos,pheroos_runtime,pheroos_bench,importlib.metadata as m; "
            "print(json.dumps({'paths':[pheroos.__file__,pheroos_runtime.__file__,pheroos_bench.__file__],"
            "'versions':{n:m.version(n) for n in ['pheroos','pheroos-runtime','pheroos-bench']}}))"], external, env))
        if (any(not Path(p).is_relative_to(site) for p in identities["paths"])
                or identities["versions"]["pheroos-runtime"] != "0.1.0.dev4"
                or identities["versions"]["pheroos-bench"] != "0.1.1.dev5"):
            raise RuntimeError("installed package cohort/source boundary mismatch")
        config = scratch / "pytest.ini"
        config.write_text("[pytest]\n")
        cases = ["tests/test_model_interface_v1.py", "integration/model-interface-v1",
                 "integration/coordination-repair-v1", "tests/test_r0_measurement.py",
                 "tests/test_r0_runtime.py", "tests/test_r0_replication.py", "tests/test_r0_cli.py"]
        test_output = run([sys.executable, "-m", "pytest", "-q", "-rs", "-c", str(config),
                           *[str(root / name) for name in cases]], external, env)
        if "skipped" in test_output:
            raise RuntimeError("required installed coverage skipped: " + test_output)
        if args.retain_wheel:
            args.retain_wheel.mkdir(parents=True, exist_ok=True)
            with (args.retain_wheel / wheel.name).open("xb") as stream:
                stream.write(wheel.read_bytes())
        report = dict(profile="model_interface_installed_consumer_v1", status="PASS", identities=identities,
            inputs=inputs, bench_wheel=wheel.name, bench_wheel_sha256=sha256(wheel.read_bytes()).hexdigest(),
            test_output=test_output, source_independent=True, live_model_calls=0, network_calls=0,
            counts_toward_verdict=False)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
