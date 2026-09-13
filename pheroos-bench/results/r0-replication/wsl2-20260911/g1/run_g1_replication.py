"""Local WSL2 G1 replication driver; preserves source and original evidence."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time

EVIDENCE = Path(__file__).resolve().parent
RUNTIME_REPO = Path('/tmp/PheroOS-runtime')
CORE_REPO = Path('/home/scott/projects/PheroOS')
RUNTIME = Path('/tmp/pheroos-wsl2-runtime-g1')
CORE = Path('/tmp/pheroos-wsl2-runtime-core')
RUNTIME_SHA = 'b3c0d4977c466c02a200d4fe63857682de53ddfd'
CORE_SHA = 'b4845e5972e74425af55ad9f306b17535957c68d'
BOOTSTRAP_PYTHON = CORE_REPO / '.venv/bin/python'
VENV = RUNTIME / '.venv'
PYTHON = VENV / 'bin/python'
EXTERNAL = EVIDENCE / 'external-cwd'
ENV = {**os.environ, 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PIP_NO_INDEX': '1',
       'PIP_NO_CACHE_DIR': '1', 'PIP_DISABLE_PIP_VERSION_CHECK': '1'}
ENV.pop('PYTHONPATH', None)


def save(name, payload):
    with (EVIDENCE / name).open('x') as handle:
        json.dump(payload, handle, indent=2)
        handle.write('\n')


def run(name, argv, cwd, *, binary=False):
    started = datetime.now(timezone.utc).isoformat()
    tick = time.monotonic()
    completed = subprocess.run([str(arg) for arg in argv], cwd=cwd, env=ENV,
                               capture_output=True)
    elapsed = time.monotonic() - tick
    (EVIDENCE / (name + ('.stdout.bin' if binary else '.stdout.log'))).write_bytes(completed.stdout)
    (EVIDENCE / (name + '.stderr.log')).write_bytes(completed.stderr)
    record = {'name': name, 'argv': [str(arg) for arg in argv], 'cwd': str(cwd),
              'started_utc': started, 'elapsed_seconds': elapsed,
              'exit_status': completed.returncode,
              'environment_overrides': {key: ENV[key] for key in ('PYTEST_DISABLE_PLUGIN_AUTOLOAD', 'PIP_NO_INDEX', 'PIP_NO_CACHE_DIR', 'PIP_DISABLE_PIP_VERSION_CHECK')},
              'removed_environment_variables': ['PYTHONPATH']}
    with (EVIDENCE / 'commands.jsonl').open('a') as handle:
        handle.write(json.dumps(record) + '\n')
    print(f'{name}: exit={completed.returncode}, elapsed={elapsed:.3f}s', flush=True)
    if completed.returncode:
        print(completed.stdout.decode(errors='replace')[-12000:], flush=True)
        print(completed.stderr.decode(errors='replace')[-12000:], flush=True)
        raise RuntimeError(f'{name} failed with {completed.returncode}')
    return completed.stdout if binary else completed.stdout.decode()


def archive(name, repo, revision, target):
    if target.exists():
        raise RuntimeError(f'Refusing existing frozen source target {target}')
    tree = run(name, ['git', 'archive', '--format=tar', revision], repo, binary=True)
    target.mkdir()
    with tarfile.open(fileobj=io.BytesIO(tree)) as bundle:
        bundle.extractall(target, filter='data')
    return {'repository': str(repo), 'commit': revision, 'source_directory': str(target),
            'archive_sha256': sha256(tree).hexdigest()}


def bootstrap():
    sources = {'runtime': archive('runtime-source-archive', RUNTIME_REPO, RUNTIME_SHA, RUNTIME),
               'core': archive('core-source-archive', CORE_REPO, CORE_SHA, CORE)}
    save('sources.json', sources)
    EXTERNAL.mkdir()
    run('create-venv', [BOOTSTRAP_PYTHON, '-m', 'venv', '--without-pip', VENV], EXTERNAL)
    target = VENV / f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
    copied = []
    for name in ('pip', 'build', 'pytest', 'setuptools', 'wheel', 'packaging',
                 'pyproject_hooks', 'iniconfig', 'pluggy', 'pygments'):
        dist = importlib.metadata.distribution(name)
        origin = Path(dist.locate_file('')).resolve()
        count = 0
        for entry in dist.files or ():
            relative = Path(entry)
            if '..' in relative.parts or relative.is_absolute():
                continue
            source = Path(dist.locate_file(entry))
            if not source.is_file():
                continue
            dest = target / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            count += 1
        copied.append({'name': name, 'version': dist.version,
                       'source_site_packages': str(origin), 'copied_files': count})
    save('offline-bootstrap.json', {
        'method': 'isolated stdlib venv without pip, populated offline from existing distribution file inventories; package scripts outside site-packages omitted',
        'include_system_site_packages': False,
        'bootstrap_interpreter': str(BOOTSTRAP_PYTHON), 'runtime_interpreter': str(PYTHON),
        'copied_distributions': copied,
        'core_and_runtime_installation': 'exact source revision wheels installed with pip --no-deps --no-index; no editable installs',
        'deviation_from_historical_environment': 'Historical macOS Python 3.14 patch/development lock unavailable; this is a newly recorded Python 3.14.7 environment.'})
    run('core-build', [PYTHON, '-m', 'build', '--no-isolation', '--wheel', '--outdir', CORE / 'dist'], CORE)
    run('runtime-build', [PYTHON, '-m', 'build', '--no-isolation', '--wheel', '--sdist', '--outdir', RUNTIME / 'dist'], RUNTIME)
    core_wheel = next((CORE / 'dist').glob('*.whl'))
    runtime_wheel = next((RUNTIME / 'dist').glob('*.whl'))
    run('install-frozen-wheels', [PYTHON, '-m', 'pip', 'install', '--no-index', '--no-deps', core_wheel, runtime_wheel], EXTERNAL)
    run('python', [PYTHON, '-VV'], EXTERNAL)
    run('packages', [PYTHON, '-m', 'pip', 'freeze', '--all'], EXTERNAL)
    run('pip-check', [PYTHON, '-m', 'pip', 'check'], EXTERNAL)
    run('kernel', ['uname', '-a'], EXTERNAL)
    run('cpu', ['lscpu'], EXTERNAL)
    run('os-release', ['cat', '/etc/os-release'], EXTERNAL)
    run('installed-paths', [PYTHON, '-c', 'import json,pheroos,pheroos_runtime,sys,sqlite3; print(json.dumps(dict(executable=sys.executable, core=pheroos.__file__, runtime=pheroos_runtime.__file__, sqlite=sqlite3.sqlite_version, sys_path=sys.path),indent=2))'], EXTERNAL)
    save('bootstrap-complete.json', {'runtime_interpreter': str(PYTHON), 'core_wheel': str(core_wheel),
                                    'runtime_wheel': str(runtime_wheel)})


def acceptance():
    bootstrap_info = json.loads((EVIDENCE / 'bootstrap-complete.json').read_text())
    run('runtime-tests', [PYTHON, '-m', 'pytest', '-q', RUNTIME / 'tests'], EXTERNAL)
    run('verify-install', [PYTHON, RUNTIME / 'tools/verify_install.py', '--core-wheel',
                          bootstrap_info['core_wheel'], '--output', EVIDENCE / 'g1-install-acceptance.json'], EXTERNAL)
    database = EVIDENCE / 'demo.sqlite'
    run('cli-create', [VENV / 'bin/pheroos-runtime', 'create', database, '--run-id', 'demo'], EXTERNAL)
    run('cli-resume', [VENV / 'bin/pheroos-runtime', 'resume', database, '--workers', '4', '--policy', 'blackboard'], EXTERNAL)
    run('cli-status', [VENV / 'bin/pheroos-runtime', 'status', database], EXTERNAL)
    run('cli-snapshot', [PYTHON, '-c',
        'import json,sys; from pathlib import Path; from pheroos_runtime.store import Store; snapshot=Store(sys.argv[1]).snapshot(); path=Path(sys.argv[2]); f=path.open("x"); json.dump(snapshot,f,indent=2); f.write("\\n"); f.close(); print(json.dumps({k:snapshot[k] for k in ("actual_units","reserved_units","unknown_units")},indent=2))',
        database, EVIDENCE / 'demo-snapshot.json'], EXTERNAL)
    artifacts = EVIDENCE / 'artifacts'
    artifacts.mkdir()
    hashes = []
    for source in (next((CORE / 'dist').glob('*.whl')), *sorted((RUNTIME / 'dist').glob('*'))):
        target = artifacts / source.name
        shutil.copy2(source, target)
        hashes.append({'artifact': str(target.relative_to(EVIDENCE)), 'source': str(source),
                       'size_bytes': target.stat().st_size, 'sha256': sha256(target.read_bytes()).hexdigest()})
    save('artifact-hashes.json', hashes)
    save('acceptance-complete.json', {'status': 'G1_WSL2_ENGINEERING_ACCEPTANCE_PASSED',
                                    'runtime_commit': RUNTIME_SHA, 'core_commit': CORE_SHA,
                                    'limitations': ['mock-only', 'no CUDA or models invoked',
                                      'original development dependency versions unavailable',
                                      'cross-platform result applies only to tested configurations']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=('bootstrap', 'acceptance'))
    args = parser.parse_args()
    (bootstrap if args.phase == 'bootstrap' else acceptance)()
