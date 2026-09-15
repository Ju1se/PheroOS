"""The installed CLI exposes only the retained local inspection path."""
from importlib.util import find_spec
import json
from pathlib import Path
import subprocess
import sys

import pytest

from pheroos_interaction.runner import cli


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / 'experiments/current/inspection-example'


def test_only_inspection_and_replay_commands_remain(capsys):
    with pytest.raises(SystemExit) as raised:
        cli.main(['--help'])
    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    assert 'inspect-replay' in help_text and 'research' not in help_text
    assert 'acquisition-simulate' not in help_text and 'math-live' not in help_text
    for removed_command in ('research', 'acquisition-simulate', 'math-live', 'api-dry-run'):
        with pytest.raises(SystemExit) as raised:
            cli.main([removed_command])
        assert raised.value.code == 2


@pytest.mark.parametrize('historical', [False, True])
def test_historical_source_mismatch_is_an_explicit_replay_option(tmp_path, monkeypatch, capsys, historical):
    from pheroos_interaction.runner import inspection

    received = []
    def replay(run_dir, require_source_match=True):
        received.append((run_dir, require_source_match))
        return {'status': 'PASS', 'mode': 'offline replay'}
    monkeypatch.setattr(inspection, 'replay_inspection', replay)
    args = ['inspect-replay', '--run', str(tmp_path)]
    if historical:
        args.append('--historical')
    assert cli.main(args) == 0
    assert received == [(tmp_path, not historical)]
    assert json.loads(capsys.readouterr().out)['mode'] == 'offline replay'


def test_retired_solvers_runners_and_provider_modules_are_absent():
    for suffix in ('acquisition', 'acquisition_baselines', 'attention', 'belief',
                   'belief_discount', 'policy', 'visibility', 'ports', 'runner.host',
                   'runner.research_cli', 'runner.adapters', 'runner.accounting'):
        assert find_spec('pheroos_interaction.' + suffix) is None, suffix


def test_active_execution_and_replay_do_not_import_research_or_providers(tmp_path):
    script = '''
import json, sys
from pheroos_interaction.runner.cli import main
main(['inspect', '--config', sys.argv[1], '--source', sys.argv[2], '--output', sys.argv[3]])
main(['inspect-replay', '--run', sys.argv[3]])
forbidden = ('pheroos_interaction.acquisition', 'pheroos_interaction.acquisition_baselines',
 'pheroos_interaction.attention', 'pheroos_interaction.belief', 'pheroos_interaction.policy',
 'pheroos_interaction.runner.host', 'pheroos_interaction.runner.research_cli',
 'pheroos_interaction.runner.adapters', 'pheroos_interaction.runner.accounting')
assert not set(forbidden).intersection(sys.modules)
assert not any(n.startswith('pheroos_interaction.experiments') for n in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', script, str(EXAMPLE / 'request.json'),
                             str(EXAMPLE / 'source'), str(tmp_path / 'run')],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert len(result.stdout.splitlines()) == 2
    for line in result.stdout.splitlines():
        assert isinstance(json.loads(line), dict)
