"""Source identity covers every installed and editable execution package."""

from hashlib import sha256
from importlib import import_module
from pathlib import Path

import pytest

from pheroos_interaction.runner.identity import source_identity


PACKAGES = (
    'pheroos_interaction',
    'pheroos_interaction.runner',
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


def test_source_identity_covers_all_retained_modules():
    identity = source_identity()
    expected = {
        'pheroos_interaction/__init__.py',
        'pheroos_interaction/records.py',
        'pheroos_interaction/inspection.py',
        'pheroos_interaction/sequential.py',
        'pheroos_interaction/commitment.py',
        'pheroos_interaction/leases.py',
        'pheroos_interaction/runner/__init__.py',
        'pheroos_interaction/runner/cli.py',
        'pheroos_interaction/runner/driver.py',
        'pheroos_interaction/runner/evidence.py',
        'pheroos_interaction/runner/session.py',
        'pheroos_interaction/runner/inspection.py',
        'pheroos_interaction/runner/identity.py',
        'pheroos_interaction/runner/platform.py',
        'pheroos_interaction/runner/policies.py',
        'pheroos_interaction/runner/provider.py',
        'pheroos_interaction/runner/worker.py',
        'pheroos_interaction/runner/colony.py',
    }
    assert set(identity) == expected
    assert all(not Path(key).is_absolute() and '..' not in Path(key).parts for key in identity)
    assert all(len(value) == 64 for value in identity.values())


@pytest.mark.parametrize('package', PACKAGES)
def test_source_identity_detects_changed_and_added_files_in_every_package(isolated_sources, package):
    before = source_identity()
    expected_keys = {name.replace('.', '/') + '/__init__.py' for name in PACKAGES}
    assert set(before) == expected_keys
    root = isolated_sources[package]
    changed = root / '__init__.py'
    original = changed.read_bytes()
    changed.write_text('# changed fixture\n')
    assert source_identity() != before
    changed.write_bytes(original)
    assert source_identity() == before
    added = root / 'nested' / 'extra.py'
    added.parent.mkdir()
    added.write_text('# newly introduced executable source\n')
    after = source_identity()
    added_key = package.replace('.', '/') + '/nested/extra.py'
    assert set(after) == expected_keys | {added_key}
    assert after[added_key] == sha256(added.read_bytes()).hexdigest()


def test_source_identity_covers_multiple_editable_roots_and_rejects_conflicts(
        tmp_path, isolated_sources, monkeypatch):
    package = import_module(PACKAGES[1])
    extra_root = tmp_path / 'external_editable_runner'
    extra_root.mkdir()
    extra = extra_root / 'extra.py'
    extra.write_text('# source outside the core directory\n')
    monkeypatch.setattr(package, '__path__', [str(isolated_sources[PACKAGES[1]]), str(extra_root)])
    assert source_identity()['pheroos_interaction/runner/extra.py'] == sha256(extra.read_bytes()).hexdigest()
    (extra_root / '__init__.py').write_text('# conflicting same package module\n')
    with pytest.raises(RuntimeError, match='conflicting source identity'):
        source_identity()
