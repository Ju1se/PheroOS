from __future__ import annotations

"""Validation and isolated application of TCK mutations/permutations."""

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from pheroos.conformance._commit_tck.models import (
    CommitTckVector,
    object_value,
    text_value,
    validate_expected_shape,
)


def validate_variants(value: object, *, permutation: bool) -> list[dict[str, Any]]:
    label = "permutations" if permutation else "mutations"
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"commit TCK {label} must be an array of objects")
    required = (
        {"id", "authority_namespace", "path", "order", "expected"}
        if permutation
        else {"id", "authority_namespace", "path", "replacement", "expected"}
    )
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(value):
        if set(raw) != required:
            raise ValueError(f"commit TCK {label}[{index}] fields are invalid")
        text_value(raw["id"], f"commit TCK {label}[{index}] id")
        namespace = raw["authority_namespace"]
        if namespace not in {"isolated", "shared"}:
            raise ValueError(
                f"commit TCK {label}[{index}] authority_namespace is invalid"
            )
        path = raw["path"]
        if (
            not isinstance(path, list)
            or not path
            or any(type(item) not in {str, int} for item in path)
        ):
            raise ValueError(f"commit TCK {label}[{index}] path is invalid")
        if path[0] not in {"manifest", "prior_authoritative_state", "inputs"}:
            raise ValueError(f"commit TCK {label}[{index}] path root is invalid")
        expected = object_value(
            raw["expected"],
            f"commit TCK {label}[{index}] expected",
        )
        validate_expected_shape(
            expected,
            label=f"commit TCK {label}[{index}] expected",
        )
        if permutation:
            order = raw["order"]
            if order != "reverse" and (
                not isinstance(order, list)
                or any(type(item) is not int or item < 0 for item in order)
            ):
                raise ValueError(f"commit TCK {label}[{index}] order is invalid")
        normalized.append(raw)
    return normalized


def variant_vector(
    vector: CommitTckVector,
    specification: Mapping[str, Any],
    *,
    permutation: bool,
) -> CommitTckVector:
    state: dict[str, Any] = {
        "manifest": deepcopy(vector.manifest),
        "prior_authoritative_state": deepcopy(vector.prior_authoritative_state),
        "inputs": deepcopy(vector.inputs),
    }
    path = list(specification["path"])
    parent, key = _resolve_parent(state, path)
    if permutation:
        current = _read_child(parent, key)
        if not isinstance(current, list):
            raise ValueError("commit TCK permutation path must select an array")
        order = specification["order"]
        if order == "reverse":
            replacement = list(reversed(current))
        else:
            if sorted(order) != list(range(len(current))):
                raise ValueError(
                    "commit TCK permutation order must be a full bijection"
                )
            replacement = [current[index] for index in order]
    else:
        replacement = deepcopy(specification["replacement"])
    _write_child(parent, key, replacement)
    return replace(
        vector,
        id=(
            vector.id
            if specification["authority_namespace"] == "shared"
            else (
                f"{vector.id}::"
                f"{'permutation' if permutation else 'mutation'}::"
                f"{specification['id']}"
            )
        ),
        manifest=state["manifest"],
        prior_authoritative_state=state["prior_authoritative_state"],
        inputs=state["inputs"],
        expected=deepcopy(specification["expected"]),
        mutations=(),
        permutations=(),
    )


def _resolve_parent(root: object, path: list[object]) -> tuple[object, object]:
    current = root
    for component in path[:-1]:
        current = _read_child(current, component)
    return current, path[-1]


def _read_child(parent: object, key: object) -> Any:
    if isinstance(parent, dict) and isinstance(key, str) and key in parent:
        return parent[key]
    if isinstance(parent, list) and type(key) is int and 0 <= key < len(parent):
        return parent[key]
    raise ValueError("commit TCK variant path does not exist")


def _write_child(parent: object, key: object, value: Any) -> None:
    if isinstance(parent, dict) and isinstance(key, str) and key in parent:
        parent[key] = value
        return
    if isinstance(parent, list) and type(key) is int and 0 <= key < len(parent):
        parent[key] = value
        return
    raise ValueError("commit TCK variant path does not exist")


__all__: list[str] = []
