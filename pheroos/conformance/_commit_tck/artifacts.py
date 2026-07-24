"""Packaged Commit TCK artifact loading, hashing, and schema generation."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from importlib import resources
import json
from pathlib import Path
from typing import Any

from pheroos.conformance._commit_tck.models import (
    EXPECTED_FIELDS,
    CommitTckVector,
    integer_value,
    object_value,
    result,
    text_value,
    validate_expected_shape,
)
from pheroos.conformance._commit_tck.mutations import validate_variants


COMMIT_TCK_VERSION = "pheroos-commit-integrity-tck-v1"
COMMIT_TCK_ARTIFACT = resources.files("pheroos.conformance").joinpath(
    "tck",
    "commit-integrity-v1.json",
)
COMMIT_TCK_SCHEMA_ID = "https://pheroos.dev/schemas/commit-tck.schema.json"

VECTOR_FIELDS = frozenset(
    {
        "id",
        "tck_version",
        "matrix_case",
        "title",
        "manifest",
        "profile",
        "prior_authoritative_state",
        "inputs",
        "expected",
        "mutations",
        "permutations",
    }
)


def load_commit_tck_vectors(
    path: str | Path | Any = None,
) -> tuple[CommitTckVector, ...]:
    source = COMMIT_TCK_ARTIFACT if path is None else Path(path)
    raw = json.loads(
        source.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(raw, dict) or set(raw) != {"tck_version", "vectors"}:
        raise ValueError("commit TCK artifact must contain tck_version and vectors")
    if raw["tck_version"] != COMMIT_TCK_VERSION:
        raise ValueError("commit TCK artifact version is unsupported")
    if not isinstance(raw["vectors"], list) or not raw["vectors"]:
        raise ValueError("commit TCK artifact requires non-empty vectors")
    vectors = tuple(_vector_from_json(item) for item in raw["vectors"])
    ids = tuple(item.id for item in vectors)
    cases = tuple(item.matrix_case for item in vectors)
    if len(ids) != len(set(ids)):
        raise ValueError("commit TCK artifact contains duplicate vector ids")
    if len(cases) != len(set(cases)):
        raise ValueError("commit TCK artifact contains duplicate matrix cases")
    if cases != tuple(range(1, 39)):
        raise ValueError("commit TCK artifact must contain matrix cases 1..38 in order")
    return vectors


def commit_tck_artifact_root(path: str | Path | Any = None) -> str:
    """Hash the complete semantic artifact without self-referential case 38."""

    source = COMMIT_TCK_ARTIFACT if path is None else Path(path)
    raw = json.loads(
        source.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
    )
    if not isinstance(raw, dict) or not isinstance(raw.get("vectors"), list):
        raise ValueError("commit TCK artifact root requires a vector artifact")
    projection = deepcopy(raw)
    case_38 = tuple(
        item
        for item in projection["vectors"]
        if isinstance(item, dict) and item.get("matrix_case") == 38
    )
    if len(case_38) != 1:
        raise ValueError("commit TCK artifact root requires exactly one case 38")
    case_38[0]["expected"] = result()
    canonical = json.dumps(
        projection,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + sha256(canonical).hexdigest()


def commit_tck_schema() -> dict[str, Any]:
    expected = {
        "type": "object",
        "required": sorted(EXPECTED_FIELDS),
        "additionalProperties": False,
        "properties": {
            "metrics": {"type": "object"},
            "roots": {"type": "object"},
            "progress": {"type": ["object", "null"]},
            "outcome": {"type": ["object", "null"]},
            "trace_sequence": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
            "certificate": {"type": ["object", "null"]},
            "failure_code": {"type": ["string", "null"], "minLength": 1},
        },
    }
    variant = {
        "type": "object",
        "required": [
            "id",
            "authority_namespace",
            "path",
            "replacement",
            "expected",
        ],
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "authority_namespace": {"enum": ["isolated", "shared"]},
            "path": {
                "type": "array",
                "minItems": 1,
                "items": {"type": ["string", "integer"]},
            },
            "replacement": {},
            "expected": expected,
        },
    }
    permutation = {
        "type": "object",
        "required": ["id", "authority_namespace", "path", "order", "expected"],
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "authority_namespace": {"enum": ["isolated", "shared"]},
            "path": {
                "type": "array",
                "minItems": 1,
                "items": {"type": ["string", "integer"]},
            },
            "order": {
                "oneOf": [
                    {"const": "reverse"},
                    {"type": "array", "items": {"type": "integer", "minimum": 0}},
                ]
            },
            "expected": expected,
        },
    }
    vector = {
        "type": "object",
        "required": sorted(VECTOR_FIELDS),
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "tck_version": {"const": COMMIT_TCK_VERSION},
            "matrix_case": {"type": "integer", "minimum": 1, "maximum": 38},
            "title": {"type": "string", "minLength": 1},
            "manifest": {"type": ["object", "null"]},
            "profile": {"type": "string", "minLength": 1},
            "prior_authoritative_state": {"type": "object"},
            "inputs": {"type": "object"},
            "expected": expected,
            "mutations": {"type": "array", "items": variant},
            "permutations": {"type": "array", "items": permutation},
        },
    }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": COMMIT_TCK_SCHEMA_ID,
        "type": "object",
        "required": ["tck_version", "vectors"],
        "additionalProperties": False,
        "properties": {
            "tck_version": {"const": COMMIT_TCK_VERSION},
            "vectors": {"type": "array", "minItems": 1, "items": vector},
        },
    }


def _vector_from_json(raw: object) -> CommitTckVector:
    value = object_value(raw, "commit TCK vector")
    if set(value) != VECTOR_FIELDS:
        missing = sorted(VECTOR_FIELDS - set(value))
        unknown = sorted(set(value) - VECTOR_FIELDS)
        raise ValueError(
            "commit TCK vector fields are invalid; "
            f"missing={missing}, unknown={unknown}"
        )
    expected = object_value(value["expected"], "commit TCK expected")
    validate_expected_shape(expected, label="commit TCK expected")
    mutations = validate_variants(value["mutations"], permutation=False)
    permutations = validate_variants(value["permutations"], permutation=True)
    manifest = value["manifest"]
    if manifest is not None and not isinstance(manifest, dict):
        raise ValueError("commit TCK manifest must be an object or null")
    matrix_case = integer_value(value["matrix_case"], "commit TCK matrix_case")
    if not 1 <= matrix_case <= 38:
        raise ValueError("commit TCK matrix_case must be in 1..38")
    tck_version = text_value(value["tck_version"], "commit TCK version")
    if tck_version != COMMIT_TCK_VERSION:
        raise ValueError("commit TCK vector version is unsupported")
    return CommitTckVector(
        id=text_value(value["id"], "commit TCK vector id"),
        tck_version=tck_version,
        matrix_case=matrix_case,
        title=text_value(value["title"], "commit TCK vector title"),
        manifest=deepcopy(manifest),
        profile=text_value(value["profile"], "commit TCK vector profile"),
        prior_authoritative_state=deepcopy(
            object_value(
                value["prior_authoritative_state"],
                "commit TCK prior_authoritative_state",
            )
        ),
        inputs=deepcopy(object_value(value["inputs"], "commit TCK inputs")),
        expected=deepcopy(expected),
        mutations=tuple(deepcopy(mutations)),
        permutations=tuple(deepcopy(permutations)),
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"commit TCK JSON contains duplicate key: {key}")
        value[key] = item
    return value


__all__ = [
    "COMMIT_TCK_ARTIFACT",
    "COMMIT_TCK_SCHEMA_ID",
    "COMMIT_TCK_VERSION",
    "commit_tck_artifact_root",
    "commit_tck_schema",
    "load_commit_tck_vectors",
]
