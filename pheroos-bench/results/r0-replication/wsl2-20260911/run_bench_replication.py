"""One-run acceptance recipe for the frozen R0 source; no model execution."""
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path('/home/scott/projects/PheroOS')
OUT = ROOT / 'pheroos-bench/results/r0-replication/wsl2-20260911'
SOURCE = Path('/tmp/pheroos-wsl2-bench-source/pheroos-bench')
PYTHON = Path('/tmp/pheroos-wsl2-bench-env/bin/python')
RUNTIME = Path('/tmp/pheroos-wsl2-runtime-g1/.venv/bin/python')
ENV = {**os.environ, 'PIP_NO_INDEX': '1', 'PIP_NO_CACHE_DIR': '1',
       'PIP_DISABLE_PIP_VERSION_CHECK': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'}
ENV.pop('PYTHONPATH', None)


def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def run(name, args, cwd=OUT):
    start = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=ENV, capture_output=True)
    for label, content in [('stdout', result.stdout), ('stderr', result.stderr)]:
        with (OUT / f'{name}.{label}.log').open('xb') as stream:
            stream.write(content)
    receipt = dict(name=name, argv=list(map(str, args)), cwd=str(cwd),
                   started_utc=start, elapsed_seconds=time.monotonic()-tick,
                   exit_status=result.returncode)
    with (OUT / 'commands.jsonl').open('a') as stream:
        stream.write(json.dumps(receipt) + '\n')
    print(f'{name}: exit={result.returncode}, elapsed={receipt["elapsed_seconds"]:.2f}s', flush=True)
    if result.returncode:
        print((result.stdout + result.stderr).decode(errors='replace')[-5000:], flush=True)
        raise RuntimeError(name)
    return result.stdout


def bootstrap():
    target = PYTHON.parent.parent / 'lib/python3.14/site-packages'
    copied = []
    for name in ('build', 'pytest', 'setuptools', 'wheel', 'packaging',
                 'pyproject_hooks', 'iniconfig', 'pluggy', 'pygments'):
        dist = importlib.metadata.distribution(name)
        for entry in dist.files or ():
            relative = Path(entry)
            if '..' in relative.parts or relative.is_absolute():
                continue
            origin = Path(dist.locate_file(entry))
            if origin.is_file():
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origin, destination)
        copied.append(dict(name=name, version=dist.version))
    save('offline-bootstrap.json', dict(
        bootstrap_interpreter=sys.executable, copied_distributions=copied,
        method='stdlib isolated venv; test/build distributions copied from existing installed file inventories; no editable or system site fallback',
        numpy='2.5.3 installed from PyPI into this venv only',
        historical_dependency_lock_available=False))
    run('bench-build', [PYTHON, '-m', 'build', '--no-isolation', '--wheel', '--sdist',
                        '--outdir', OUT / 'artifacts'], SOURCE)
    core = Path('/tmp/pheroos-wsl2-bench-core-wheel/pheroos-0.1.0-py3-none-any.whl')
    shutil.copy2(core, OUT / 'artifacts' / core.name)
    wheel = next((OUT / 'artifacts').glob('pheroos_bench*.whl'))
    run('install-frozen-wheels', [PYTHON, '-m', 'pip', 'install', '--no-deps',
                                 '--no-build-isolation', core, wheel])
    run('pip-check', [PYTHON, '-m', 'pip', 'check'])
    run('packages', [PYTHON, '-m', 'pip', 'freeze', '--all'])
    run('python', [PYTHON, '-VV'])
    run('kernel', ['uname', '-a'])
    run('cpu', ['lscpu'])
    run('os-release', ['cat', '/etc/os-release'])
    run('installed-paths', [PYTHON, '-c', 'import json,sys,sqlite3,pheroos,pheroos_bench;print(json.dumps(dict(python=sys.version,sqlite=sqlite3.sqlite_version,core=pheroos.__file__,bench=pheroos_bench.__file__,sys_path=sys.path),indent=2))'])
    sources = {'bench_commit': 'b154472becea561ac1f5fc442a7ccf372ab154f8',
               'bench_core_commit': '4f292de799b01e57bdbb87e915191f310d219579',
               'runtime_commit': 'b3c0d4977c466c02a200d4fe63857682de53ddfd',
               'runtime_core_commit': 'b4845e5972e74425af55ad9f306b17535957c68d',
               'runtime_handoff_commit': 'e3ef1e8',
               'source_method': 'git archive from exact revisions; independent venvs and installed wheels'}
    save('sources.json', sources)
    save('artifact-hashes.json', {p.name: sha256(p.read_bytes()).hexdigest()
                                 for p in sorted((OUT / 'artifacts').iterdir())})


def acceptance():
    run('bench-tests', [PYTHON, '-m', 'pytest', '-q', SOURCE / 'tests'], SOURCE)
    refs = SOURCE / 'results/r0/runtime'
    def checks(name, directory):
        args = [PYTHON, '-m', 'pheroos_bench.r0_self_check', '--output', OUT / f'{name}.json']
        for case in ('completed', 'cancelled_unknown', 'cancelled_late_receipt'):
            args += ['--runtime-snapshot', directory / f'{case}.json']
        run(name, args)
    checks('stored-snapshot-checks', refs)
    run('capture-fresh-runtime', [RUNTIME, SOURCE / 'tools/capture_r0_runtime.py',
                                '--output', OUT / 'runtime'])
    checks('fresh-snapshot-checks', OUT / 'runtime')
    old = json.loads((SOURCE / 'results/r0/instrument-checks-v2.json').read_text())
    new = json.loads((OUT / 'stored-snapshot-checks.json').read_text())
    save('stored-report-comparison.json', dict(
        exact_report_equal=old == new,
        historical_report_sha256=sha256((SOURCE / 'results/r0/instrument-checks-v2.json').read_bytes()).hexdigest(),
        replication_report_sha256=sha256((OUT / 'stored-snapshot-checks.json').read_bytes()).hexdigest(),
        counts_toward_verdict=False))
    assert old == new, 'stored-snapshot report changed'


if __name__ == '__main__':
    {'bootstrap': bootstrap, 'acceptance': acceptance}[sys.argv[1]]()
