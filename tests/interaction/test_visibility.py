"""Small counterexamples for the extracted, frozen interaction semantics."""

import json
import subprocess
import sys

import pytest

from pheroos_interaction import policy, visibility
from pheroos_interaction.experiments.current.evaluation import score_v1, score_v2
from pheroos_interaction.experiments.current.fixtures import source_values_v1, source_values_v2


def record(identifier, owner, source, version, value):
    return dict(id=identifier, kind="source", owner=owner, readers=["a", "b"], round_index=0,
                body=dict(source_id=source, source_version=version, value=value),
                parents=["root:" + source], provenance_known=True)


def materialize(r):
    current = r["body"]["source_version"] == 2
    return dict(value=r["body"], metadata=dict(publisher=r["owner"], current=current,
        superseded=not current, source_id=r["body"]["source_id"], source_version=r["body"]["source_version"]))


def test_core_imports_have_no_runner_ground_truth_or_legacy_dependency():
    code = """
import sys
from pheroos_interaction import records, visibility, policy, ports
assert not any(n == 'pheroos_interaction.experiments' or n.startswith('pheroos_interaction.experiments.') for n in sys.modules)
assert not any(n == 'pheroos' or n.startswith('pheroos.') or n.startswith('pheroos_runtime') for n in sys.modules)
assert not any(n == 'pheroos_interaction.runner' or n.startswith('pheroos_interaction.runner.') for n in sys.modules)
"""
    subprocess.run([sys.executable, "-I", "-c", code], check=True)


def test_public_versions_are_separate_from_ground_truth_values():
    assert visibility.public_task("shared_update", 0)["source_versions"] == {"factor": 1, "offset": 1}
    assert visibility.public_task("shared_update", 1)["source_versions"] == {"factor": 2, "offset": 1}
    assert source_values_v1("shared_update", 1)["factor"]["value"] == 6
    assert source_values_v2("fresh_b/stale", 2)["bias"]["value"] == -2
    with pytest.raises(ValueError, match="undeclared world or round"):
        visibility.public_task("shared_update", 3)


@pytest.mark.parametrize("raw", ['{"action":"inspect","target":"unknown"}',
    '{"action":"submit","answer":1,"answer":13,"citations":[]}',
    '{"action":"submit","answer":true,"citations":[]}'])
def test_exact_parser_rejections_are_preserved(raw):
    expected = dict(valid=False, action=None, reason="invalid_json_action_or_window")
    assert visibility.parse_action(raw, 1, [], world_id="simple_arithmetic") == expected
    assert policy.parse_action(raw, 1, ["multiplier", "bias"], world_id="fresh_a/complete") == expected


def test_stale_projection_is_explicit_and_does_not_become_current_citation():
    records = [record("mine", "a", "multiplier", 2, 4), record("peer-old", "b", "bias", 1, 8)]
    context = policy.build_request("fresh_a/stale", "a", "eligibility_current", 1, records, materialize)
    assert context["sent_record_ids"] == ["mine", "peer-old"]
    assert context["state_diagnostics"]["missing_current_sources"] == ["bias"]
    sent = json.loads(context["messages"][1]["content"])
    assert sent["visible"][1]["eligible_for_current_citation"] is False
    assert "state_diagnostics" not in sent and "stale" not in sent["task"].values()
    parsed = policy.parse_action('{"action":"submit","answer":23,"citations":[{"source_id":"multiplier","source_version":2},{"source_id":"bias","source_version":2}]}',
                                    2, ["multiplier", "bias"], world_id="fresh_a/stale")
    assert score_v2("fresh_a/stale", parsed)
    assert not policy.current_citations("fresh_a/stale", parsed, context)


def test_peer_new_inspection_does_not_rescue_another_agent_and_order_is_real():
    records = [record("mine", "a", "multiplier", 2, 4), record("peer", "b", "bias", 2, 3)]
    records[1]["round_index"] = 1
    context = policy.build_request("fresh_a/missing", "a", "owner_current", 2, records, materialize)
    assert context["sent_record_ids"] == ["mine"]
    records[1]["owner"] = "a"
    context2 = policy.build_request("fresh_a/missing", "a", "owner_current", 2, records, materialize)
    assert context2["sent_record_ids"] == ["mine", "peer"]
    assert context2["messages_sha256"] != context["messages_sha256"]


def test_currentness_and_publisher_checks_keep_original_rejection_reason():
    r = record("mine", "a", "multiplier", 2, 4)
    def bad_metadata(item):
        result = materialize(item)
        result["metadata"]["publisher"] = "b"
        return result
    with pytest.raises(ValueError, match="source content, publisher or currentness differs from Session read"):
        policy.build_request("fresh_a/missing", "a", "owner_current", 1, [r], bad_metadata)


def test_score_semantics_stay_value_only_and_boolean_is_not_integer():
    parsed = visibility.parse_action('{"action":"submit","answer":13,"citations":[]}', 0, [], world_id="simple_arithmetic")
    assert score_v1("simple_arithmetic", 0, parsed)
    parsed["action"]["answer"] = True
    assert not score_v1("simple_arithmetic", 0, parsed)


def test_missing_and_cyclic_ancestry_stays_unknown():
    r = dict(id="a", kind="proposal", owner="a", parents=["a", "missing"], provenance_known=True)
    result = visibility.ancestry(["a"], [r])
    assert result["unknown_provenance"] == ["cycle:a", "missing"]
