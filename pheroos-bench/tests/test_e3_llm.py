from __future__ import annotations

import json
from threading import Barrier
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
def test_authenticated_requests_keep_headers_and_body_on_stdin_without_retries(
    monkeypatch, embedding
):
    commands = []
    request_options = []
    prompt = 'one "quoted"\\path\n第二行'
    monkeypatch.setenv("E3_TEST_KEY", "test-key")

    def request(command, **kwargs):
        commands.append(command)
        request_options.append(kwargs)
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
        llm._embed(**common, inputs=[prompt])
    else:
        llm._chat(
            **common,
            prompt=prompt,
            temperature=0.6,
            top_p=0.95,
            max_tokens=20,
            answer_type="numeric",
        )
    command = commands[0]
    options = request_options[0]
    config = [line.split(" = ", 1) for line in options["input"].splitlines()]
    headers = [json.loads(value) for key, value in config if key == "header"]
    assert headers == [
        "Content-Type: application/json",
        "Authorization: Bearer test-key",
    ]
    body = next(json.loads(value) for key, value in config if key == "data-binary")
    payload = json.loads(body)
    actual_prompt = (
        payload["input"][0] if embedding else payload["messages"][-1]["content"]
    )
    assert actual_prompt == prompt
    assert command[:2] == ["curl", "-q"]
    assert command[-2:] == ["--config", "-"]
    assert "test-key" not in " ".join(command)
    assert prompt not in " ".join(command)
    assert "E3_TEST_KEY" not in options["env"]
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
        max_calls=2,
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
            max_calls=1,
            model="mock-v1",
        )
    assert calls == []


@pytest.mark.parametrize("max_calls", [None, 0, -1, True, 1.5, 1])
def test_runner_checks_explicit_call_cap_before_submission(
    tmp_path, monkeypatch, max_calls
):
    calls = []
    monkeypatch.setattr(llm, "_chat", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(ValueError):
        llm.run(
            api_key=None,
            items=[{"item_id": "one", "question": "q", "answer": "1"}],
            output=tmp_path / "run",
            n=2,
            repetitions=1,
            workers=1,
            max_calls=max_calls,
        )
    assert calls == []
    assert not (tmp_path / "run").exists()


def test_dry_run_requires_no_credentials_or_output_and_makes_no_calls(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "items.jsonl"
    path.write_text(json.dumps({"question": "1+1?", "answer": "2"}) + "\n")
    monkeypatch.delenv("E3_DRY_RUN_TEST_KEY", raising=False)
    calls = []
    monkeypatch.setattr(llm, "_post_json", lambda **kwargs: calls.append(kwargs))
    assert (
        llm.main(
            [
                "--items",
                str(path),
                "--dry-run",
                "--api-key-env",
                "E3_DRY_RUN_TEST_KEY",
                "--n",
                "2",
                "--repetitions",
                "3",
                "--max-tokens",
                "20",
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["dry_run"] is True
    assert preview["call_count"] == 6
    assert preview["completion_tokens_upper_bound"] == 120
    assert preview["total_tokens_upper_bound"] is None
    assert preview["monetary_upper_bound"] is None
    assert calls == []
    assert list(tmp_path.iterdir()) == [path]


def test_live_cli_requires_explicit_call_limit(tmp_path, monkeypatch):
    path = tmp_path / "items.jsonl"
    path.write_text(json.dumps({"question": "1+1?", "answer": "2"}) + "\n")
    calls = []
    monkeypatch.setattr(llm, "_post_json", lambda **kwargs: calls.append(kwargs))
    with pytest.raises(SystemExit) as exc:
        llm.main(["--items", str(path), "--output", str(tmp_path / "run")])
    assert exc.value.code == 2
    assert calls == []


@pytest.mark.parametrize(
    "defect", ["transport", "model_drift", "missing_choices", "invalid_answer"]
)
def test_failure_stops_later_batches_and_preserves_every_valid_usage_receipt(
    tmp_path, monkeypatch, defect
):
    started = []
    peers = Barrier(2)

    def post(**kwargs):
        question = kwargs["payload"]["messages"][-1]["content"]
        started.append(question)
        peers.wait(timeout=5)
        payload = {
            "id": question,
            "model": "mock-v1",
            "choices": [{"message": {"content": "#### 1"}}],
            "usage": _response()["usage"],
        }
        if question == "fail":
            if defect == "transport":
                raise RuntimeError("request failed")
            if defect == "model_drift":
                payload["model"] = "drift-v2"
            elif defect == "missing_choices":
                payload["choices"] = []
            else:
                payload["choices"][0]["message"]["content"] = "#### 1/0"
        return payload

    monkeypatch.setattr(llm, "_post_json", post)
    with pytest.raises((ValueError, RuntimeError)):
        llm.run(
            api_key=None,
            items=[
                {"item_id": name, "question": name, "answer": "1"}
                for name in ("fail", "peer", "later-1", "later-2")
            ],
            output=tmp_path / "run",
            n=1,
            repetitions=1,
            workers=2,
            max_calls=4,
            model="mock-v1",
        )
    assert sorted(started) == ["fail", "peer"]
    metadata = json.loads((tmp_path / "run" / "metadata.json").read_text())
    receipts = [
        json.loads(line)
        for line in (tmp_path / "run" / "calls.ndjson").read_text().splitlines()
    ]
    expected_receipts = 1 if defect == "transport" else 2
    assert metadata["status"] == "ABORTED"
    assert metadata["calls_attempted"] == 2
    assert metadata["receipted_calls"] == len(receipts) == expected_receipts
    assert metadata["usable_calls"] == 1
    assert metadata["known_tokens"] == 5 * expected_receipts
    assert metadata["unknown_spend"] is (defect == "transport")
    assert not (tmp_path / "run" / "admission.ndjson").exists()
    if defect != "transport":
        invalid = next(row for row in receipts if row["item_id"] == "fail")
        assert invalid["status"] == "INVALID"
        assert invalid["counts_toward_verdict"] is False
        assert invalid["total_tokens"] == 5
        assert "quality" not in invalid
