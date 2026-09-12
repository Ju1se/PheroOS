from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from pheroos_bench import e3_llm as llm


def _response() -> dict:
    return {
        "text": "#### 1",
        "answer": "1",
        "model": "mock-v1",
        "response_id": "id",
        "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }


@pytest.mark.parametrize("embedding", [False, True])
def test_authenticated_requests_have_separate_headers_and_no_hidden_retries(
    monkeypatch, embedding
):
    commands = []

    def request(command, **kwargs):
        commands.append(command)
        payload = {
            "model": "mock-v1",
            "choices": [{"message": {"content": "#### 1"}}],
            "usage": _response()["usage"],
            "data": [{"index": 0, "embedding": [1.0, 0.0]}],
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(llm.subprocess, "run", request)
    common = dict(
        api_key="test-key", base_url="https://example.invalid/v1", model="mock-v1"
    )
    if embedding:
        llm._embed(**common, inputs=["one"])
    else:
        llm._chat(
            **common,
            prompt="one",
            temperature=0.6,
            top_p=0.95,
            max_tokens=20,
            answer_type="numeric",
        )
    command = commands[0]
    headers = [command[i + 1] for i, value in enumerate(command) if value == "-H"]
    assert headers == [
        "Content-Type: application/json",
        "Authorization: Bearer test-key",
    ]
    assert "--retry" not in command


def _run(tmp_path, monkeypatch, response):
    monkeypatch.setattr(llm, "_chat", lambda **kwargs: response)
    return llm.run(
        api_key=None,
        items=[{"item_id": "item-1", "question": "one", "answer": "1"}],
        output=tmp_path / "run",
        benchmark="other-benchmark",
        n=2,
        repetitions=1,
        workers=1,
        model="mock-v1",
    )


def test_runner_records_actual_benchmark_and_known_spend(tmp_path, monkeypatch):
    metadata = _run(tmp_path, monkeypatch, _response())
    row = json.loads((tmp_path / "run" / "admission.ndjson").read_text())
    assert row["cell"] == "other-benchmark"
    assert row["arm"] == "static_homog@2"
    assert row["phase"] == "admission"
    assert row["counts_toward_verdict"] is False
    assert row["tokens"] == metadata["total_tokens"] == 10


@pytest.mark.parametrize(
    "defect",
    [
        "missing_usage",
        "missing_completion",
        "inconsistent_usage",
        "negative_usage",
        "model_drift",
    ],
)
def test_runner_rejects_unknown_cost_or_model_drift(tmp_path, monkeypatch, defect):
    response = _response()
    if defect == "missing_usage":
        response["usage"] = {}
    elif defect == "missing_completion":
        del response["usage"]["completion_tokens"]
    elif defect == "inconsistent_usage":
        response["usage"]["total_tokens"] = 0
    elif defect == "negative_usage":
        response["usage"]["completion_tokens"] = -1
    else:
        response["model"] = "different-v2"
    with pytest.raises(ValueError):
        _run(tmp_path, monkeypatch, response)
    assert not (tmp_path / "run" / "admission.ndjson").exists()


def test_embedding_uses_indices_to_preserve_input_order(monkeypatch):
    payload = {
        "model": "mock-v1",
        "usage": {"prompt_tokens": 2, "total_tokens": 2},
        "data": [
            {"index": 1, "embedding": [0.0, 1.0]},
            {"index": 0, "embedding": [1.0, 0.0]},
        ],
    }
    monkeypatch.setattr(
        llm.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout=json.dumps(payload), stderr=""
        ),
    )
    result = llm._embed(
        api_key=None,
        base_url="http://localhost:11434/v1",
        model="mock-v1",
        inputs=["a", "b"],
    )
    assert result["vectors"] == [[1.0, 0.0], [0.0, 1.0]]


@pytest.mark.parametrize(
    "defect", ["missing_answer", "null_answer", "empty_answer", "empty_question"]
)
def test_item_loader_rejects_missing_ground_truth_or_question(tmp_path, defect):
    item = {"question": "1+1?", "answer": "2"}
    if defect == "missing_answer":
        del item["answer"]
    elif defect == "null_answer":
        item["answer"] = None
    elif defect == "empty_answer":
        item["answer"] = "#### "
    else:
        item["question"] = " "
    path = tmp_path / "items.jsonl"
    path.write_text(json.dumps(item) + "\n")
    with pytest.raises(ValueError):
        llm._load_items(path, None)


@pytest.mark.parametrize(
    "defect", ["empty_answer", "empty_question", "duplicate_id", "no_items"]
)
def test_runner_rejects_invalid_items_before_any_call(tmp_path, monkeypatch, defect):
    items = [{"item_id": "one", "question": "1+1?", "answer": "2"}]
    if defect == "empty_answer":
        items[0]["answer"] = ""
    elif defect == "empty_question":
        items[0]["question"] = " "
    elif defect == "duplicate_id":
        items.append(dict(items[0]))
    else:
        items = []
    calls = []
    monkeypatch.setattr(
        llm, "_chat", lambda **kwargs: calls.append(kwargs) or _response()
    )
    with pytest.raises(ValueError):
        llm.run(
            api_key=None,
            items=items,
            output=tmp_path / "run",
            n=1,
            repetitions=1,
            workers=1,
            model="mock-v1",
        )
    assert calls == []
