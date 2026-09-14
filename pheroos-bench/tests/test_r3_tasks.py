import json

import pytest

from pheroos_bench.r3_tasks import DATA_VERSION, public_view, verify, world_ids


def code(text):
    return json.dumps({"code": text})


def evidence(lane, max_units, version):
    return json.dumps(
        {
            "answer": {"lane": lane, "max_units": max_units},
            "citations": [
                {"source_id": "policy", "version": 1},
                {"source_id": "capacity", "version": version},
            ],
        }
    )


def test_world_grid_is_fixed_and_views_are_detached():
    expected = [
        "code_repair/clamp", "code_repair/chunk_count",
        "evidence_revision/dispatch_limit", "evidence_revision/channel_route",
    ]
    assert world_ids() == expected
    world_ids().clear()
    assert world_ids() == expected
    for world in world_ids():
        view = public_view(world, 0)
        assert view["data_version"] == DATA_VERSION
        assert "hidden" not in json.dumps(view)
        assert "answer" not in view  # Input schemas are not completed answers.
        view["instruction"] = "mutated"
        assert public_view(world, 0)["instruction"] != "mutated"
    view = public_view(expected[0], 0)
    view["visible_tests"][0]["expected"] = 999
    assert public_view(expected[0], 0)["visible_tests"][0]["expected"] == 0


@pytest.mark.parametrize(
    "world,source",
    [
        ("code_repair/clamp", "def clamp(value, lower, upper):\n    return max(lower, min(value, upper))"),
        ("code_repair/chunk_count", "def chunk_count(total, width):\n    return (total + width - 1) // width"),
    ],
)
def test_correct_repairs_pass_visible_and_hidden_checks(world, source):
    result = verify(world, 0, code(source))
    assert result["valid"]
    assert result["artifact"]["verification"] == "visible_checks_only"
    assert result["artifact"]["candidate"]["code"] == source
    final = verify(world, 3, code(source), final=True)
    assert final == {"valid": True, "feedback": "Final verification complete.", "artifact": None}


def test_conditionals_locals_docstrings_and_boolean_expressions_are_supported():
    source = '''def clamp(value, lower, upper):
    """Clamp an integer."""
    result = value
    if value < lower or value == lower:
        result = lower
    elif not (value < upper):
        result = upper
    return result
'''
    assert verify("code_repair/clamp", 0, code(source), final=True)["valid"]


def test_integer_ternary_abs_and_modulo_are_supported():
    source = "def chunk_count(total, width):\n    return abs(total) // width + (1 if total % width else 0)"
    assert verify("code_repair/chunk_count", 0, code(source), final=True)["valid"]


@pytest.mark.parametrize("world", ["code_repair/clamp", "code_repair/chunk_count"])
def test_original_bug_fails_a_public_check(world):
    result = verify(world, 0, code(public_view(world, 0)["source"]))
    assert not result["valid"]
    assert "Visible tests failed" in result["feedback"]
    assert result["artifact"] is None


@pytest.mark.parametrize(
    "world,source",
    [
        ("code_repair/clamp", "def clamp(value, lower, upper):\n    return max(0, min(value, 5))"),
        ("code_repair/chunk_count", "def chunk_count(total, width):\n    return total // width + (1 if total == 9 else 0)"),
    ],
)
def test_hidden_cases_reject_visible_case_overfitting_without_feedback_leak(world, source):
    assert verify(world, 1, code(source))["valid"]
    final = verify(world, 3, code(source), final=True)
    assert final == {"valid": False, "feedback": "Final verification complete.", "artifact": None}


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef clamp(value, lower, upper):\n    return value",
        "def clamp(value, lower, upper):\n    return __import__('os').system('true')",
        "def clamp(value, lower, upper):\n    return value.__class__",
        "def clamp(value, lower, upper):\n    while True:\n        pass",
        "def clamp(value, lower, upper):\n    return clamp(value, lower, upper)",
        "def clamp(value, lower, upper):\n    return 2 ** 1000000000",
        "def clamp(value, lower, upper):\n    return [value][0]",
        "def clamp(value, lower, upper):\n    return 1 / 2",
        "@abs\ndef clamp(value, lower, upper):\n    return value",
        "def clamp(value, lower, upper=5):\n    return value",
        "def clamp(value, lower, upper):\n    return min(value=value)",
        "def clamp(value, lower, upper):\n    min = 3\n    return max(lower, min(value, upper))",
        "def clamp(value, lower, upper):\n    return True",
        "def clamp(value, lower, upper):\n    return 1 // 0",
        "def clamp(value, lower, upper):\n    return missing",
        "def clamp(value, lower, upper):\n    x = 1000000000000 * 1000000000000\n    return x",
        "def clamp(value, lower, upper):\n    if False:\n        import os\n    return max(lower, min(value, upper))",
        "def clamp(value, lower, upper):\n    x = 1",
    ],
)
def test_generated_code_cannot_escape_or_exceed_the_finite_subset(source):
    result = verify("code_repair/clamp", 0, code(source))
    assert result["valid"] is False
    assert result["artifact"] is None


def test_syntax_and_text_size_are_bounded():
    source = "def clamp(value, lower, upper):\n    return " + "+".join(["1"] * 150)
    assert not verify("code_repair/clamp", 0, code(source))["valid"]
    assert not verify("code_repair/clamp", 0, " " * 20_000)["valid"]
    assert not verify("code_repair/clamp", 0, code("x" * 9_000))["valid"]


@pytest.mark.parametrize(
    "world,before,after",
    [
        ("evidence_revision/dispatch_limit", ("blue", 6), ("blue", 3)),
        ("evidence_revision/channel_route", ("alpha", 2), ("beta", 4)),
    ],
)
def test_source_update_is_fixed_and_stale_citations_are_rejected(world, before, after):
    for step in (0, 1):
        assert public_view(world, step)["task_version"] == 1
        assert verify(world, step, evidence(*before, 1))["valid"]
    for step in (2, 3):
        assert public_view(world, step)["task_version"] == 2
        stale_answer = verify(world, step, evidence(*before, 1))
        assert not stale_answer["valid"]
        assert "current source" in stale_answer["feedback"]
        assert not verify(world, step, evidence(*after, 1))["valid"]
        wrong_answer = verify(world, step, evidence(*before, 2))
        assert not wrong_answer["valid"]
        assert wrong_answer["feedback"] == "The answer does not satisfy the current cross-document constraints."
        corrected = verify(world, step, evidence(*after, 2))
        assert corrected["valid"]
        assert corrected["artifact"]["task_version"] == 2
        assert corrected["artifact"]["verification"] == "current_sources_checked"
    assert verify(world, 3, evidence(*after, 2), final=True)["valid"]


def test_evidence_citations_must_be_exact_current_distinct_sources():
    valid = json.loads(evidence("blue", 3, 2))
    mutations = [
        [valid["citations"][0], valid["citations"][0]],
        [valid["citations"][0]],
        [{"source_id": "policy", "version": True}, {"source_id": "capacity", "version": 2}],
        [{"source_id": "policy", "version": 1}, {"source_id": "capacity", "version": "2"}],
        [{"source_id": "policy", "version": 1}, {"source_id": "other", "version": 2}],
    ]
    for citations in mutations:
        result = verify("evidence_revision/dispatch_limit", 3, json.dumps(valid | {"citations": citations}))
        assert not result["valid"]
    valid["citations"].reverse()
    assert verify("evidence_revision/dispatch_limit", 3, json.dumps(valid))["valid"]


def test_evidence_answer_requires_exact_fields_and_nonboolean_integer():
    valid = json.loads(evidence("blue", 3, 2))
    for answer in [
        {"lane": "blue", "max_units": True},
        {"lane": "blue", "max_units": 3, "confidence": 1},
        {"lane": "blue"},
        {"lane": "blue", "max_units": "3"},
    ]:
        assert not verify(
            "evidence_revision/dispatch_limit", 3, json.dumps(valid | {"answer": answer})
        )["valid"]


@pytest.mark.parametrize(
    "text",
    [
        "[]", "null", '{"code":"a","code":"b"}',
        '{"code":NaN}', '{"code":"a","extra":1}',
        'Here is JSON: {"code":"a"}', '```python\n{"code":"a"}\n```',
        '{"answer":{"lane":"blue","max_units":true},"citations":[]}',
    ],
)
def test_strict_response_schema_rejects_extra_text_duplicate_keys_and_nonfinite_data(text):
    assert not verify("code_repair/clamp", 0, text)["valid"]


def test_one_json_fence_is_accepted_but_extra_fences_are_not():
    text = code("def clamp(value, lower, upper):\n    return max(lower, min(value, upper))")
    assert verify("code_repair/clamp", 0, "```json\n" + text + "\n```")["valid"]
    assert verify("code_repair/clamp", 0, "```\n" + text + "\n```")["valid"]
    assert not verify("code_repair/clamp", 0, "```json\n" + text + "\n```\n```\nextra\n```")["valid"]


def test_final_feedback_hides_failure_kind_and_has_no_artifact():
    cases = [
        ("code_repair/clamp", "not JSON"),
        ("code_repair/clamp", code("def clamp(value, lower, upper):\n    return 1 // 0")),
        ("evidence_revision/dispatch_limit", evidence("blue", 6, 1)),
        ("evidence_revision/dispatch_limit", evidence("green", 5, 2)),
    ]
    for world, text in cases:
        assert verify(world, 3, text, final=True) == {
            "valid": False, "feedback": "Final verification complete.", "artifact": None,
        }


def test_invalid_world_step_and_final_flag_are_caller_errors():
    for world, step in [("unknown", 0), ("code_repair/clamp", -1), ("code_repair/clamp", True)]:
        with pytest.raises(ValueError):
            public_view(world, step)
        with pytest.raises(ValueError):
            verify(world, step, "{}")
    with pytest.raises(ValueError):
        verify("code_repair/clamp", 0, "{}", final=1)
