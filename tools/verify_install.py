"""Run with a fresh installed Python -I, outside any source tree; no network."""
import argparse
from contextlib import ExitStack, redirect_stdout
from hashlib import sha256
from importlib import metadata, util
import io
import json
from pathlib import Path
import socket
import sys
from time import perf_counter
from unittest.mock import patch
import zipfile


def hashes(directory):
    return {str(p.relative_to(directory)): sha256(p.read_bytes()).hexdigest()
            for p in sorted(directory.rglob('*')) if p.is_file()}


def denied(*args, **kwargs):
    raise AssertionError('forbidden credential, money-ledger or network effect')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--v1', type=Path, required=True)
    parser.add_argument('--v2', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    inputs = [args.v1.resolve(), args.v2.resolve()]
    assert all((p / 'frozen-config.json').is_file() for p in inputs), 'retained run directories required'
    assert sys.flags.isolated and sys.prefix != sys.base_prefix
    assert all(output != p and not output.is_relative_to(p) and not p.is_relative_to(output) for p in inputs)
    output.mkdir(parents=True, exist_ok=False)
    assert all(util.find_spec(name) is None for name in ('pheroos', 'pheroos_runtime', 'pheroos_bench', 'numpy'))
    dist = metadata.distribution('pheroos-interaction')
    assert all('extra ==' in r for r in dist.requires or [])
    assert not any(p.suffix == '.pth' and 'editable' in p.name
                   for p in Path(sys.prefix).rglob('*.pth'))
    installed = Path(dist.locate_file('pheroos_interaction')).resolve()
    assert installed.is_relative_to(Path(sys.prefix).resolve())
    with zipfile.ZipFile(args.wheel) as wheel:
        members = wheel.namelist()
        assert all(n.startswith(('pheroos_interaction/', 'pheroos_interaction-0.1.0.dev1.dist-info/')) for n in members)
        package_members = [n for n in members if n.startswith('pheroos_interaction/')]
        assert all(n.endswith('.py') for n in package_members)
        for name in package_members:
            assert wheel.read(name) == Path(dist.locate_file(name)).read_bytes()
    before = [hashes(p) for p in inputs]
    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, 'connect', denied))
        stack.enter_context(patch.object(socket, 'create_connection', denied))
        start = perf_counter()
        from pheroos_interaction import visibility, factorial
        pure_ms = (perf_counter() - start) * 1000
        assert not any('pheroos_interaction.' + name in sys.modules
                       for name in ('adapters', 'accounting', 'fixtures', 'evaluation', 'host'))
        pure_loaded = sorted(n for n in sys.modules if n.startswith('pheroos_interaction'))
        start = perf_counter()
        from pheroos_interaction.cli import main as cli
        cli_ms = (perf_counter() - start) * 1000
        # These are never executed; patching makes the dry-run claim falsifiable.
        from pheroos_interaction import adapters, accounting
        stack.enter_context(patch.object(adapters, '_credential', denied))
        stack.enter_context(patch.object(adapters.KimiCNAdapter, '_http', denied))
        stack.enter_context(patch.object(accounting.MoneyLedger, '__init__', denied))
        log = io.StringIO()
        with redirect_stdout(log):
            start = perf_counter()
            assert cli(['mock', '--output', str(output / 'mock')]) == 0
            mock_ms = (perf_counter() - start) * 1000
            assert cli(['api-dry-run', '--output', str(output / 'dry')]) == 0
            for version, source in zip(('v1', 'v2'), inputs):
                assert cli(['replay', '--run', str(source), '--output', str(output / version)]) == 0
        (output / 'cli.log').write_text(log.getvalue())
    after = [hashes(p) for p in inputs]
    assert before == after
    loaded = {name: str(Path(module.__file__).resolve()) for name, module in sys.modules.copy().items()
              if name.startswith('pheroos_interaction') and getattr(module, '__file__', None)}
    assert all(Path(path).is_relative_to(installed) for path in loaded.values())
    assert not any(name.split('.')[0] in {'pheroos', 'pheroos_runtime', 'pheroos_bench', 'numpy'} for name in sys.modules)
    report = dict(status='PASS', python=sys.version, executable=sys.executable, cwd=str(Path.cwd()),
        isolated=True, sys_path=sys.path, package_path=str(installed), requires_dist=dist.requires or [],
        runtime_required_dependencies=[], wheel=str(args.wheel.resolve()), wheel_bytes=args.wheel.stat().st_size,
        wheel_sha256=sha256(args.wheel.read_bytes()).hexdigest(), package_members=len(package_members),
        installed_package_matches_wheel=True, pure_modules=pure_loaded, dynamic_modules=loaded,
        timing_ms=dict(pure_import=pure_ms, additional_cli_import=cli_ms, mock_after_import=mock_ms),
        timing_limit='Single instrumented warm-cache sample; not a performance benchmark.',
        forbidden_effects_patched=['socket.connect', 'socket.create_connection', 'credential', 'adapter._http', 'MoneyLedger.__init__'],
        credential_reads=0, new_provider_calls=0, money_ledger_opened=False,
        historical_inputs_unchanged=True, input_files=sum(map(len, before)),
        replay={v: json.loads((output / v / 'report.json').read_text()) for v in ('v1', 'v2')})
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('status', 'package_path', 'package_members', 'historical_inputs_unchanged', 'new_provider_calls')}))


if __name__ == '__main__':
    main()
