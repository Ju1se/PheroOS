from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import pytest

from pheroos_bench import r3_tool_tasks as tasks


_PATH = Path(__file__).parents[1] / "tools/audit_r3_format.py"
_SPEC = importlib.util.spec_from_file_location("audit_r3_format", _PATH)
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


@pytest.mark.parametrize("text,category", [
    ('```json\n{"action":"inspect","target":"above_upper"}\n```', "sole_json_fence_object"),
    (' \n```json\r\n{"action":"inspect"}\r\n```\n', "sole_json_fence_object"),
    ('```python\nprint(1)\n```', "sole_python_fence"),
    ('```JSON\n{}\n```', "sole_other_fence"),
    ('```\n{}\n```', "sole_other_fence"),
    ('```json\n[]\n```', "sole_json_fence_invalid_object"),
    ('```json\n{"x":1,"x":2}\n```', "sole_json_fence_invalid_object"),
    ('```json\n{"x":NaN}\n```', "sole_json_fence_invalid_object"),
    ('```json\n{"x":Infinity}\n```', "sole_json_fence_invalid_object"),
    ('```json\n{} {}\n```', "sole_json_fence_invalid_object"),
    ('Here is JSON:\n```json\n{}\n```', "fence_with_prose_or_multiple_blocks"),
    ('```json\n{}\n```\nExplanation', "fence_with_prose_or_multiple_blocks"),
    ('```json\n{}\n```\n```json\n{}\n```', "fence_with_prose_or_multiple_blocks"),
    ('{}', "bare_json_object"),
    ('not JSON', "other_prose_or_invalid_json"),
])
def test_only_one_exact_json_object_fence_is_eligible(text, category):
    actual = audit.classify(text)
    assert actual["class"] == category
    assert (actual["body"] is not None) == (category == "sole_json_fence_object")


def _row(text, step=0, memory=None):
    memory = [] if memory is None else memory
    return {"world_id": "code_repair/clamp", "step": step,
            "request": {"messages": tasks.messages_for("code_repair/clamp", step, memory)},
            "response": {"text": text},
            "result": tasks.apply("code_repair/clamp", step, memory, text)}


def test_unwrap_admission_does_not_change_original_receipt_or_history():
    row = _row('```json\n{"action":"inspect","target":"above_upper"}\n```')
    memory = []
    original = deepcopy((row, memory))
    result = audit.evaluate_call(row, memory)
    assert result["original_result"]["valid"] is False
    assert result["posthoc_result"]["valid"] is True
    assert result["posthoc_result"]["artifact"]["receipt"]["passed"] is False
    assert (row, memory) == original


def test_valid_json_does_not_repair_placeholder_target():
    result = audit.evaluate_call(_row('```json\n{"action":"inspect","target":"index_entry"}\n```'), [])
    assert result["normalization_attempted"] is True
    assert result["posthoc_result"]["valid"] is False
    assert "unknown" in result["posthoc_result"]["feedback"]


def test_unwrap_does_not_repair_embedded_newlines_in_code_lines():
    text = json.dumps({"action": "submit", "candidate": {"code_lines": [
        "def clamp(value, lower, upper):\n", "    return max(lower, min(value, upper))"]}})
    result = audit.evaluate_call(_row("```json\n" + text + "\n```"), [])
    assert result["normalization_attempted"] is True
    assert result["posthoc_result"]["valid"] is False
    assert "exactly one source line" in result["posthoc_result"]["feedback"]


def test_noneligible_response_is_never_sent_to_normalized_checker(monkeypatch):
    row = _row('Explanation:\n```json\n{"action":"inspect","target":"above_upper"}\n```')
    original_apply = tasks.apply
    calls = []
    def apply(*args):
        calls.append(args)
        return original_apply(*args)
    monkeypatch.setattr(tasks, "apply", apply)
    result = audit.evaluate_call(row, [])
    assert len(calls) == 1
    assert result["normalization_attempted"] is False
    assert result["posthoc_result"] is None


def test_tampered_original_receipt_or_prompt_refuses_analysis():
    row = _row('```json\n{"action":"inspect","target":"above_upper"}\n```')
    row["result"]["valid"] = True
    with pytest.raises(ValueError, match="does not reproduce"):
        audit.evaluate_call(row, [])
    row = _row('```json\n{"action":"inspect","target":"above_upper"}\n```')
    row["request"]["messages"][0]["content"] += " changed"
    with pytest.raises(ValueError, match="original public history"):
        audit.evaluate_call(row, [])


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "sentinel"
    sentinel.write_text("preserved")
    with pytest.raises(ValueError, match="overwrite"):
        audit.main(["--source", str(tmp_path), "--runtime-source", str(tmp_path), "--output", str(output)])
    assert sentinel.read_text() == "preserved"
