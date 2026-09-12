"""Small Kimi-compatible E3 admission/pilot runner.

The runner is intentionally outside protocol-core and uses the OpenAI-shaped
HTTP API through ``curl``.  It records model responses and usage, but never
persists the API key.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any


DEFAULT_BASE_URL = "https://api.moonshot.cn/v1"
DEFAULT_MODEL = "kimi-k2.6"


class _ChatResponseError(ValueError):
    """An unusable answer can still carry a valid, billable usage receipt."""

    def __init__(self, message: str, response: dict[str, Any], usage: dict[str, int]):
        super().__init__(message)
        self.receipt = {
            "status": "INVALID",
            "model": response.get("model"),
            "response_id": response.get("id", response.get("response_id")),
            **usage,
        }


def _token_usage(usage: Any, *, embedding: bool = False) -> dict[str, int]:
    names = (
        ("prompt_tokens", "total_tokens")
        if embedding
        else ("prompt_tokens", "completion_tokens", "total_tokens")
    )
    if not isinstance(usage, dict) or any(
        type(usage.get(name)) is not int or usage[name] < 0 for name in names
    ):
        raise ValueError("token usage is missing or invalid; unknown spend is not zero")
    expected = usage["prompt_tokens"] + (0 if embedding else usage["completion_tokens"])
    if usage["total_tokens"] < expected or (
        not embedding and usage["total_tokens"] != expected
    ):
        raise ValueError("inconsistent token accounting")
    return {name: usage[name] for name in names}


def _unwrap_boxed(value: str) -> str:
    marker = "\\boxed{"
    start = value.find(marker)
    if start < 0:
        return value
    depth = 0
    for index in range(start + len(marker) - 1, len(value)):
        char = value[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return value[start + len(marker) : index]
    return value


def _normalise_frac(value: str) -> str:
    marker = "\\frac{"
    while marker in value:
        start = value.find(marker)
        numerator_start = start + len(marker)
        depth = 1
        index = numerator_start
        while index < len(value) and depth:
            depth += value[index] == "{"
            depth -= value[index] == "}"
            index += 1
        if depth:
            break
        numerator = value[numerator_start : index - 1]
        if index >= len(value) or value[index] != "{":
            break
        denominator_start = index + 1
        depth = 1
        index = denominator_start
        while index < len(value) and depth:
            depth += value[index] == "{"
            depth -= value[index] == "}"
            index += 1
        if depth:
            break
        denominator = value[denominator_start : index - 1]
        value = value[:start] + numerator + "/" + denominator + value[index:]
    return value


def _canonical_answer(value: str) -> str:
    value = value.strip()
    value = _unwrap_boxed(value)
    value = value.replace("$", "").replace("\\left", "").replace("\\right", "")
    value = value.replace("\\!", "").replace("\\,", "").replace("\\displaystyle", "")
    value = value.replace(" ", "").replace("\n", "")
    value = value.replace("\\dfrac", "\\frac")
    value = _normalise_frac(value)
    if re.fullmatch(r"[A-Ea-e]", value):
        return value.upper()
    value = value.replace(",", "")
    value = value.strip("$ ")
    if value.endswith("."):
        value = value[:-1]
    try:
        if "/" in value:
            numerator, denominator = (int(part) for part in value.split("/", 1))
            from fractions import Fraction

            return str(Fraction(numerator, denominator))
        number = float(value)
    except ValueError:
        return value.lower()
    if number.is_integer():
        return str(int(number))
    return format(number, ".12g")


def extract_answer(text: str, answer_type: str = "numeric") -> str:
    marked = re.findall(r"####\s*(.+?)(?:\n|$)", text)
    if marked:
        value = marked[-1].strip().strip(".`")
        return value.upper() if answer_type == "choice" else _canonical_answer(value)
    if answer_type == "choice":
        choices = re.findall(
            r"(?:answer|option)(?:\s+is)?\s*[:\[(]?\s*([A-E])\b",
            text,
            flags=re.IGNORECASE,
        )
        return choices[-1].upper() if choices else ""
    if "\\boxed{" in text:
        return _canonical_answer(_unwrap_boxed(text))
    candidates = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?(?:/\d+)?", text)
    return _canonical_answer(candidates[-1]) if candidates else ""


def _post_json(
    *, url: str, api_key: str | None, payload: dict[str, Any]
) -> dict[str, Any]:
    """Send headers and JSON through stdin, never through the process argv."""
    if api_key and any(char in api_key for char in "\r\n\0"):
        raise ValueError("API key must not contain header control characters")

    def quoted(value: str) -> str:
        # curl config understands these escapes; JSON's other control-character
        # escapes are already inside the serialized body and remain literal.
        return (
            '"'
            + value.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            + '"'
        )

    config = [
        "url = " + quoted(url),
        'header = "Content-Type: application/json"',
        "data-binary = "
        + quoted(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
    ]
    if api_key:
        config.append("header = " + quoted(f"Authorization: Bearer {api_key}"))
    # -q must be first: a user's curlrc must not add retries, tracing or redirects.
    # Retrying a paid POST can spend twice without a second usage receipt.
    process = subprocess.run(
        ["curl", "-q", "-sS", "--fail-with-body", "--max-time", "120", "--config", "-"],
        input="\n".join(config) + "\n",
        check=False,
        capture_output=True,
        text=True,
        env={key: value for key, value in os.environ.items() if value != api_key},
    )
    if process.returncode:
        message = process.stderr.strip() or process.stdout.strip() or "request failed"
        raise RuntimeError(
            message.replace(api_key, "[REDACTED]") if api_key else message
        )
    return json.loads(process.stdout)


def _chat(
    *,
    api_key: str | None,
    base_url: str,
    model: str,
    prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    answer_type: str,
) -> dict[str, Any]:
    if answer_type == "choice":
        instruction = "Choose the correct option and end with #### followed by one letter A, B, C, or D."
    else:
        instruction = "Show concise reasoning and end with #### followed by the final numeric answer."
    payload = {
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": ("Solve the problem accurately. " + instruction),
            },
            {"role": "user", "content": prompt},
        ],
    }
    # Kimi uses its ``thinking`` object; Ollama's OpenAI-compatible endpoint
    # uses ``think=false``.  Keep the distinction explicit so local models do
    # not consume the answer budget in a hidden reasoning field.
    if "127.0.0.1" in base_url or "localhost" in base_url:
        payload["think"] = False
    else:
        payload["thinking"] = {"type": "disabled"}
    response = _post_json(
        url=f"{base_url.rstrip('/')}/chat/completions",
        api_key=api_key,
        payload=payload,
    )
    usage = _token_usage(response.get("usage"))
    try:
        if response.get("model") != model:
            raise ValueError("response model differs from the declared exact model")
        choice = response["choices"][0]["message"]
        text = str(choice.get("content") or "")
        answer = extract_answer(text, answer_type)
    except Exception as error:
        raise _ChatResponseError(str(error), response, usage) from error
    return {
        "text": text,
        "answer": answer,
        "usage": usage,
        "model": response["model"],
        "response_id": response.get("id"),
    }


def _embed(
    *,
    api_key: str | None,
    base_url: str,
    model: str,
    inputs: list[str],
) -> dict[str, Any]:
    """Call an OpenAI-compatible embeddings endpoint without persisting keys."""

    if not inputs:
        raise ValueError("inputs must not be empty")
    response = _post_json(
        url=f"{base_url.rstrip('/')}/embeddings",
        api_key=api_key,
        payload={"model": model, "input": inputs},
    )
    usage = _token_usage(response.get("usage"), embedding=True)
    if response.get("model") != model:
        raise ValueError("embedding model differs from the declared exact model")
    entries = response["data"]
    if any(type(entry.get("index")) is not int for entry in entries) or sorted(
        entry["index"] for entry in entries
    ) != list(range(len(inputs))):
        raise ValueError("embedding indices must match input indices exactly")
    vectors = [
        list(map(float, entry["embedding"]))
        for entry in sorted(entries, key=lambda x: x["index"])
    ]
    if len(vectors) != len(inputs):
        raise RuntimeError("embedding response count does not match input count")
    dimensions = {len(vector) for vector in vectors}
    if (
        len(dimensions) != 1
        or 0 in dimensions
        or any(not math.isfinite(v) for vector in vectors for v in vector)
    ):
        raise RuntimeError("embedding vectors have inconsistent dimensions")
    return {
        "model": response["model"],
        "vectors": vectors,
        "usage": usage,
    }


def _validate_items(items: list[dict[str, str]]) -> None:
    if not items:
        raise ValueError("at least one labeled item is required")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key].strip()
            for key in ("item_id", "question", "answer")
        ):
            raise ValueError(
                "items require nonempty string IDs, questions, and ground truth"
            )
        if item["item_id"] in seen:
            raise ValueError("item IDs must be distinct within a benchmark")
        seen.add(item["item_id"])


def _load_items(
    path: Path, limit: int | None, benchmark: str = "gsm8k"
) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("each JSONL item must be an object")
            raw_answer = value.get("answer")
            if type(raw_answer) not in (str, int, float) or (
                isinstance(raw_answer, float) and not math.isfinite(raw_answer)
            ):
                raise ValueError("each item requires a known ground-truth answer")
            answer = str(raw_answer)
            answer = answer.split("####")[-1].strip()
            items.append(
                {
                    "item_id": f"{benchmark}-{index:04d}",
                    "question": value.get("question", value.get("problem", "")),
                    "answer": _canonical_answer(answer),
                }
            )
            if limit is not None and len(items) >= limit:
                break
    _validate_items(items)
    return items


def _majority(values: list[str]) -> str:
    counts = Counter(values)
    first_seen = {value: index for index, value in enumerate(values)}
    return min(counts, key=lambda value: (-counts[value], first_seen[value], value))


def plan_run(
    *,
    items: list[dict[str, str]],
    n: int,
    repetitions: int,
    workers: int,
    max_tokens: int,
) -> dict[str, Any]:
    """No API/tokenizer calls; max_tokens bounds completion, not total spend."""
    _validate_items(items)
    if any(type(v) is not int or v <= 0 for v in (n, repetitions, workers, max_tokens)):
        raise ValueError(
            "n, repetitions, workers, and max_tokens must be positive integers"
        )
    calls = len(items) * repetitions * n
    return {
        "arm": "single" if n == 1 else f"static_homog@{n}",
        "items": len(items),
        "n": n,
        "repetitions": repetitions,
        "call_count": calls,
        "max_in_flight": min(workers, calls),
        "completion_tokens_upper_bound": calls * max_tokens,
        "prompt_tokens_upper_bound": None,
        "total_tokens_upper_bound": None,
        "monetary_upper_bound": None,
        "scope": "one arm; sum separate invocations for the whole experiment",
        "cost_note": "Input tokens and current model prices are not known; max_tokens is not a total-token or dollar cap.",
    }


def run(
    *,
    api_key: str | None,
    items: list[dict[str, str]],
    output: Path,
    benchmark: str = "gsm8k",
    n: int,
    repetitions: int,
    workers: int,
    max_calls: int,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.6,
    top_p: float = 0.95,
    max_tokens: int = 1024,
    answer_type: str = "numeric",
    phase: str = "admission",
) -> dict[str, Any]:
    plan = plan_run(
        items=items,
        n=n,
        repetitions=repetitions,
        workers=workers,
        max_tokens=max_tokens,
    )
    if type(max_calls) is not int or max_calls <= 0:
        raise ValueError("an explicit positive max_calls limit is required")
    if plan["call_count"] > max_calls:
        raise ValueError(
            f"planned {plan['call_count']} calls exceed max_calls={max_calls}"
        )
    if phase not in ("admission", "pilot"):
        raise ValueError("this runner supports admission and void pilot only")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("output directory already contains records")
    calls: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    tasks = [
        (item, repetition, agent_index)
        for item in items
        for repetition in range(repetitions)
        for agent_index in range(n)
    ]

    def one(task: tuple[dict[str, str], int, int]) -> dict[str, Any]:
        item, repetition, agent_index = task
        identity = {
            "item_id": item["item_id"],
            "repetition": repetition,
            "agent_index": agent_index,
            "arm": "single" if n == 1 else f"static_homog@{n}",
            "phase": phase,
            "counts_toward_verdict": False,
            "expected_answer": item["answer"],
        }
        try:
            response = _chat(
                api_key=api_key,
                base_url=base_url,
                model=model,
                prompt=item["question"],
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                answer_type=answer_type,
            )
            usage = _token_usage(response["usage"])
            if response["model"] != model:
                raise _ChatResponseError(
                    "model version changed during the run", response, usage
                )
        except _ChatResponseError as error:
            error.receipt.update(identity)
            raise
        return {
            **identity,
            "model": response["model"],
            "response_id": response["response_id"],
            "answer": response["answer"],
            "quality": float(response["answer"] == item["answer"]),
            "prompt_tokens": usage["prompt_tokens"],
            "completion_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "response": response["text"],
        }

    output.mkdir(parents=True, exist_ok=True)
    # Flush each valid usage receipt, including unusable answers and peers of a
    # failed request. Submit one worker-sized batch at a time so a failure cannot
    # dispatch the rest of the paid run. Failed requests may have unknown spend.
    attempted = 0
    with (output / "calls.ndjson").open("x", encoding="utf-8") as handle:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            for offset in range(0, len(tasks), workers):
                batch = tasks[offset : offset + workers]
                futures = [executor.submit(one, task) for task in batch]
                attempted += len(futures)
                error = None
                for future in as_completed(futures):
                    try:
                        record = future.result()
                    except Exception as exc:
                        error = error or exc
                        record = (
                            exc.receipt if isinstance(exc, _ChatResponseError) else None
                        )
                    else:
                        calls.append(record)
                    if record is not None:
                        receipts.append(record)
                        handle.write(
                            json.dumps(record, ensure_ascii=False, sort_keys=True)
                            + "\n"
                        )
                        handle.flush()
                if error is not None:
                    (output / "metadata.json").write_text(
                        json.dumps(
                            {
                                "status": "ABORTED",
                                "phase": phase,
                                "model": model,
                                "counts_toward_verdict": False,
                                "plan": plan,
                                "calls_attempted": attempted,
                                "receipted_calls": len(receipts),
                                "usable_calls": len(calls),
                                "known_tokens": sum(
                                    row["total_tokens"] for row in receipts
                                ),
                                "unknown_spend": attempted > len(receipts),
                                "error_type": type(error).__name__,
                            },
                            indent=2,
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                    raise error
    calls.sort(key=lambda row: (row["item_id"], row["repetition"], row["agent_index"]))

    aggregate: list[dict[str, Any]] = []
    for item in items:
        for repetition in range(repetitions):
            for arm in sorted({row["arm"] for row in calls}):
                values = [
                    row
                    for row in calls
                    if row["item_id"] == item["item_id"]
                    and row["repetition"] == repetition
                    and row["arm"] == arm
                ]
                predicted = _majority([row["answer"] for row in values])
                aggregate.append(
                    {
                        "item_id": item["item_id"],
                        "cell": benchmark,
                        "phase": phase,
                        "counts_toward_verdict": False,
                        "repetition": repetition,
                        "arm": arm,
                        "model": values[0]["model"],
                        "quality": float(predicted == item["answer"]),
                        "predicted_answer": predicted,
                        "expected_answer": item["answer"],
                        "tokens": sum(row["total_tokens"] for row in values),
                        "agent_calls": len(values),
                    }
                )

    with (output / "admission.ndjson").open("w", encoding="utf-8") as handle:
        for row in aggregate:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    metadata = {
        "status": "COMPLETE",
        "benchmark": benchmark,
        "phase": phase,
        "counts_toward_verdict": False,
        "items": len(items),
        "n": n,
        "repetitions": repetitions,
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "answer_type": answer_type,
        "call_count": len(calls),
        "total_tokens": sum(row["total_tokens"] for row in calls),
        "api_key_recorded": False,
        "max_calls": max_calls,
        "plan": plan,
    }
    (output / "metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a small Kimi-compatible E3 chat pilot/admission"
    )
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--max-calls",
        type=int,
        help="Required hard call-count cap for a live invocation",
    )
    parser.add_argument("--benchmark", default="gsm8k")
    parser.add_argument("--phase", choices=("admission", "pilot"), default="admission")
    parser.add_argument("--api-key-env", default="MOONSHOT_API_KEY")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--n", type=int, default=16)
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--temperature", type=float, default=0.6)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument(
        "--answer-type", choices=("numeric", "choice"), default="numeric"
    )
    args = parser.parse_args(argv)
    items = _load_items(args.items, args.limit, args.benchmark)
    plan = plan_run(
        items=items,
        n=args.n,
        repetitions=args.repetitions,
        workers=args.workers,
        max_tokens=args.max_tokens,
    )
    if args.dry_run:
        print(
            json.dumps(
                {"dry_run": True, "phase": args.phase, "model": args.model, **plan},
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    if args.output is None or args.max_calls is None:
        parser.error(
            "live collection requires --output and --max-calls; preview with --dry-run"
        )
    api_key = os.environ.get(args.api_key_env) if args.api_key_env else None
    local_endpoint = "127.0.0.1" in args.base_url or "localhost" in args.base_url
    if not api_key and not local_endpoint:
        raise SystemExit(f"missing API key environment variable: {args.api_key_env}")
    metadata = run(
        api_key=api_key,
        items=items,
        output=args.output,
        n=args.n,
        repetitions=args.repetitions,
        workers=args.workers,
        max_calls=args.max_calls,
        base_url=args.base_url,
        model=args.model,
        temperature=args.temperature,
        top_p=args.top_p,
        max_tokens=args.max_tokens,
        benchmark=args.benchmark,
        answer_type=args.answer_type,
        phase=args.phase,
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
