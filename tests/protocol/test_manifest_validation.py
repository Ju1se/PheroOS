from pheroos.protocol import load_capability_manifest, validate_capability_manifest


def test_toy_manifest_validates_without_errors() -> None:
    manifest = load_capability_manifest("examples/toy-protocol/capability.json")

    diagnostics = validate_capability_manifest(manifest)

    assert diagnostics == []
