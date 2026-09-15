"""Package moves must preserve the complete fixed-rollout source boundary."""

from hashlib import sha256
from importlib import import_module
from pathlib import Path

import pytest

from pheroos_interaction.runner import host


PACKAGES = (
    'pheroos_interaction',
    'pheroos_interaction.runner',
    'pheroos_interaction.experiments',
    'pheroos_interaction.experiments.current',
)


@pytest.fixture
def isolated_sources(tmp_path, monkeypatch):
    """Redirect enumeration only; never change real or installed source files."""
    roots = {}
    for name in PACKAGES:
        root = tmp_path / name.replace('.', '_')
        root.mkdir()
        (root / '__init__.py').write_text('# isolated source identity fixture\n')
        monkeypatch.setattr(import_module(name), '__path__', [str(root)])
        roots[name] = root
    return roots


def test_source_identity_covers_installed_core_runner_and_experiment_modules():
    identity = host._source_identity()
    for key in (
        'pheroos_interaction/records.py',
        'pheroos_interaction/visibility.py',
        'pheroos_interaction/policy.py',
        'pheroos_interaction/ports.py',
        'pheroos_interaction/runner/host.py',
        'pheroos_interaction/runner/accounting.py',
        'pheroos_interaction/experiments/__init__.py',
        'pheroos_interaction/experiments/current/evaluation.py',
        'pheroos_interaction/experiments/current/replay.py',
    ):
        assert key in identity
    assert all(not Path(key).is_absolute() and '..' not in Path(key).parts for key in identity)
    assert all(len(value) == 64 for value in identity.values())


@pytest.mark.parametrize('package', [PACKAGES[1], PACKAGES[3]])
def test_source_identity_detects_changed_and_added_runner_or_experiment_files(isolated_sources, package):
    before = host._source_identity()
    expected_keys = {name.replace('.', '/') + '/__init__.py' for name in PACKAGES}
    assert set(before) == expected_keys
    root = isolated_sources[package]
    changed = root / '__init__.py'
    original = changed.read_bytes()
    changed.write_text('# changed fixture\n')
    assert host._source_identity() != before
    changed.write_bytes(original)
    assert host._source_identity() == before
    added = root / 'nested' / 'extra.py'
    added.parent.mkdir()
    added.write_text('# newly introduced executable source\n')
    after = host._source_identity()
    added_key = package.replace('.', '/') + '/nested/extra.py'
    assert set(after) == expected_keys | {added_key}
    assert after[added_key] == sha256(added.read_bytes()).hexdigest()


@pytest.mark.parametrize('package', [PACKAGES[1], PACKAGES[3]])
def test_rollout_stops_before_next_dispatch_if_new_runner_or_experiment_source_appears(
    tmp_path, isolated_sources, package
):
    class SourceChangingModel(host.MockModel):
        calls = 0

        def generate(self, messages, max_new_tokens, seed):
            self.calls += 1
            response = super().generate(messages, max_new_tokens, seed)
            (isolated_sources[package] / 'added_during_rollout.py').write_text('# source drift\n')
            return response

    model = SourceChangingModel()
    result = host.run_episode(tmp_path / 'run', world_id='fresh_a/complete', model=model)
    assert not result['complete'] and result['error_type'] == 'RuntimeError'
    assert model.calls == 1
    assert sum(row['status'] == 'UNSTARTED' for row in result['calls']) == 3
    assert all(row['quality'] is None for row in result['calls'])
