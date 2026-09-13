"""Small closed R3 pilot tasks and deterministic, non-executing verifiers.

These research fixtures do not define a core ABI or an efficacy gate. Generated
Python is interpreted through a finite integer-expression subset; it is never
passed to ``exec``, ``eval``, a shell, or an unrestricted Python process. Hidden
cases remain inside the final scorer and are never returned as model feedback.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import json
import re


DATA_VERSION = "r3_task_fixtures_v1"
_WORLDS = (
    "code_repair/clamp",
    "code_repair/chunk_count",
    "evidence_revision/dispatch_limit",
    "evidence_revision/channel_route",
)
_MAX_TEXT = 16_384
_MAX_CODE = 8_192
_MAX_NODES = 256
_MAX_INTEGER = 10**12
_MAX_STEPS = 1_024

_CODE = {
    "code_repair/clamp": {
        "name": "clamp",
        "arguments": ["value", "lower", "upper"],
        "contract": (
            "Repair clamp(value, lower, upper). All arguments are integers and "
            "lower <= upper. Return value when it is within the inclusive "
            "bounds, lower when below lower, and upper when above upper."
        ),
        "source": (
            "def clamp(value, lower, upper):\n"
            "    return max(lower, min(value, upper - 1))\n"
        ),
        "visible": [
            ("below_lower", (-2, 0, 5), 0),
            ("inside_bounds", (2, 0, 5), 2),
            ("above_upper", (9, 0, 5), 5),
        ],
        "hidden": [
            ((-8, -5, -1), -5),
            ((-2, -5, -1), -2),
            ((3, -5, -1), -1),
            ((4, 4, 4), 4),
            ((-9, 4, 4), 4),
            ((5, 0, 5), 5),
            ((7, 2, 11), 7),
        ],
    },
    "code_repair/chunk_count": {
        "name": "chunk_count",
        "arguments": ["total", "width"],
        "contract": (
            "Repair chunk_count(total, width). total is a nonnegative integer "
            "and width is a positive integer. Return the number of chunks "
            "needed to hold total items with at most width items per chunk. "
            "A final partial chunk counts as one; zero items need zero chunks."
        ),
        "source": "def chunk_count(total, width):\n    return total // width\n",
        "visible": [
            ("empty", (0, 4), 0),
            ("full_chunks", (8, 4), 2),
            ("partial_chunk", (9, 4), 3),
        ],
        "hidden": [
            ((1, 4), 1),
            ((5, 1), 5),
            ((7, 3), 3),
            ((3, 8), 1),
            ((16, 8), 2),
            ((0, 1), 0),
            ((100, 9), 12),
        ],
    },
}


def world_ids() -> list[str]:
    """Return the fixed paired-world grid in declared order."""
    return list(_WORLDS)


def _identity(world_id: str, step: int) -> None:
    if type(world_id) is not str or world_id not in _WORLDS:
        raise ValueError("undeclared R3 world")
    if type(step) is not int or step < 0:
        raise ValueError("step must be a nonnegative integer")


def _documents(world_id: str, step: int) -> list[dict]:
    version = 1 if step < 2 else 2
    if world_id == "evidence_revision/dispatch_limit":
        policy = {"selected_lane": "blue", "request_limit": 6}
        capacity = {"blue": 9, "green": 4} if version == 1 else {"blue": 3, "green": 8}
    else:
        policy = {
            "required_state": "ready",
            "request_limit": 5,
            "tie_break": "lexicographically smallest lane ID",
        }
        capacity = (
            {
                "alpha": {"state": "ready", "units": 2},
                "beta": {"state": "hold", "units": 7},
            }
            if version == 1
            else {
                "alpha": {"state": "hold", "units": 2},
                "beta": {"state": "ready", "units": 4},
            }
        )
    return [
        {"source_id": "policy", "version": 1, "content": policy},
        {"source_id": "capacity", "version": version, "content": capacity},
    ]


def public_view(world_id: str, step: int) -> dict:
    """Return only declared inputs and visible checks, detached from fixtures.

    Source updates occur at the same fixed step (2) in every arm. The caller
    supplies earlier artifacts separately; this function cannot see an arm,
    model response, hidden answer, or strategy state.
    """
    _identity(world_id, step)
    view = {
        "data_version": DATA_VERSION,
        "world_id": world_id,
        "family": world_id.split("/", 1)[0],
        "step": step,
        "task_version": 1,
        "instruction": "",
        "output_schema": {},
    }
    if world_id in _CODE:
        task = _CODE[world_id]
        view.update(
            instruction=(
                task["contract"]
                + " Return one JSON object with exactly the key code, whose "
                "string value contains the complete replacement function. "
                "Use only integer arithmetic (+, -, *, //, %), comparisons, "
                "boolean conditions, if/else, local assignments, returns, "
                "and min/max/abs. No imports, loops, attributes, or external "
                "calls. Keep the exact function name and parameter names."
            ),
            output_schema={"code": "complete Python function as a string"},
            source=task["source"],
            visible_tests=[
                {"name": name, "arguments": list(args), "expected": expected}
                for name, args, expected in task["visible"]
            ],
        )
    else:
        rule = (
            "Select the lane named by policy.selected_lane."
            if world_id == "evidence_revision/dispatch_limit"
            else "Select a lane whose current state equals policy.required_state; "
            "if several qualify, use the declared tie_break."
        )
        view.update(
            task_version=1 if step < 2 else 2,
            instruction=(
                "Answer using only the current closed documents below. "
                + rule
                + " max_units is the smaller of policy.request_limit and the "
                "selected lane's current capacity (its integer value or units "
                "field). New source versions replace old versions. Return one "
                "JSON object with exactly answer and citations. answer must "
                "contain exactly lane (a string) and max_units (an integer). "
                "Cite both current sources exactly once with their source_id "
                "and integer version. Do not include commentary."
            ),
            output_schema={
                "answer": {"lane": "selected lane ID", "max_units": "integer"},
                "citations": [{"source_id": "source ID", "version": "integer"}],
            },
            documents=_documents(world_id, step),
            source_update_step=2,
        )
    return deepcopy(view)


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError("nonfinite JSON")


def _candidate(text: str) -> dict:
    if type(text) is not str or len(text) > _MAX_TEXT:
        raise ValueError("response must be a JSON object within the text limit")
    value = text.strip()
    fence = re.fullmatch(r"```(?:json)?[ \t]*\n(.*?)\n```", value, re.DOTALL)
    if fence is not None:
        value = fence.group(1)
    candidate = json.loads(
        value,
        object_pairs_hook=_object,
        parse_constant=_nonfinite,
    )
    if type(candidate) is not dict:
        raise ValueError("response must be a JSON object")
    return candidate


class _RejectedCode(ValueError):
    pass


class _Returned(Exception):
    def __init__(self, value):
        self.value = value


class _IntegerFunction:
    """Bounded interpreter for the exact pure subset exposed by these tasks."""

    def __init__(self, code: str, name: str, arguments: list[str]):
        if type(code) is not str or len(code) > _MAX_CODE:
            raise _RejectedCode("code must be a string within the source limit")
        try:
            module = ast.parse(code)
        except (SyntaxError, RecursionError) as exc:
            raise _RejectedCode("invalid Python function syntax") from exc
        if len(list(ast.walk(module))) > _MAX_NODES:
            raise _RejectedCode("function exceeds syntax size limit")
        if len(module.body) != 1 or type(module.body[0]) is not ast.FunctionDef:
            raise _RejectedCode("provide exactly one function")
        function = module.body[0]
        params = function.args
        if (
            function.name != name
            or [arg.arg for arg in params.args] != arguments
            or params.posonlyargs
            or params.kwonlyargs
            or params.defaults
            or params.kw_defaults
            or params.vararg is not None
            or params.kwarg is not None
            or function.decorator_list
            or function.returns is not None
            or getattr(function, "type_params", [])
            or any(arg.annotation is not None for arg in params.args)
        ):
            raise _RejectedCode("use the exact undecorated function signature")
        self.arguments = arguments
        self.body = function.body
        if self.body and isinstance(self.body[0], ast.Expr):
            value = self.body[0].value
            if isinstance(value, ast.Constant) and type(value.value) is str:
                self.body = self.body[1:]  # A leading docstring has no execution effect.
        for statement in self.body:
            self._check_statement(statement)

    @staticmethod
    def _integer(value):
        if type(value) not in (int, bool) or abs(value) > _MAX_INTEGER:
            raise _RejectedCode("expression exceeded the bounded integer subset")
        return value

    def _check_statement(self, statement):
        if isinstance(statement, ast.Return):
            self._check_expression(statement.value)
        elif isinstance(statement, ast.Assign):
            if len(statement.targets) != 1 or type(statement.targets[0]) is not ast.Name:
                raise _RejectedCode("only one local variable may be assigned at a time")
            if statement.targets[0].id in ("min", "max", "abs"):
                raise _RejectedCode("local assignments must not shadow the allowed builtins")
            self._check_expression(statement.value)
        elif isinstance(statement, ast.If):
            self._check_expression(statement.test)
            for child in statement.body + statement.orelse:
                self._check_statement(child)
        else:
            raise _RejectedCode("unsupported statement; use assignment, if/else, return")

    def _check_expression(self, expression):
        if isinstance(expression, ast.Constant):
            self._integer(expression.value)
        elif isinstance(expression, ast.Name):
            pass
        elif isinstance(expression, ast.BinOp) and type(expression.op) in (
            ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod
        ):
            self._check_expression(expression.left)
            self._check_expression(expression.right)
        elif isinstance(expression, ast.UnaryOp) and type(expression.op) in (
            ast.UAdd, ast.USub, ast.Not
        ):
            self._check_expression(expression.operand)
        elif isinstance(expression, ast.BoolOp) and type(expression.op) in (ast.And, ast.Or):
            for value in expression.values:
                self._check_expression(value)
        elif isinstance(expression, ast.Compare) and all(
            type(op) in (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)
            for op in expression.ops
        ):
            for value in [expression.left, *expression.comparators]:
                self._check_expression(value)
        elif isinstance(expression, ast.IfExp):
            for value in (expression.test, expression.body, expression.orelse):
                self._check_expression(value)
        elif (
            isinstance(expression, ast.Call)
            and type(expression.func) is ast.Name
            and expression.func.id in ("min", "max", "abs")
            and not expression.keywords
            and (
                len(expression.args) == 1
                if expression.func.id == "abs"
                else 2 <= len(expression.args) <= 8
            )
        ):
            for value in expression.args:
                self._check_expression(value)
        else:
            raise _RejectedCode("unsupported expression in bounded integer subset")

    def _tick(self):
        self.steps += 1
        if self.steps > _MAX_STEPS:
            raise _RejectedCode("function exceeds evaluation limit")

    def _expression(self, node, local):
        self._tick()
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in local:
                raise _RejectedCode("undefined local variable")
            return local[node.id]
        if isinstance(node, ast.BinOp):
            left, right = self._expression(node.left, local), self._expression(node.right, local)
            operations = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.FloorDiv: lambda: left // right,
                ast.Mod: lambda: left % right,
            }
            return self._integer(operations[type(node.op)]())
        if isinstance(node, ast.UnaryOp):
            value = self._expression(node.operand, local)
            return self._integer(
                +value if isinstance(node.op, ast.UAdd)
                else -value if isinstance(node.op, ast.USub)
                else not value
            )
        if isinstance(node, ast.BoolOp):
            for expression in node.values:
                value = self._expression(expression, local)
                if isinstance(node.op, ast.And) and not value:
                    return value
                if isinstance(node.op, ast.Or) and value:
                    return value
            return value
        if isinstance(node, ast.Compare):
            left = self._expression(node.left, local)
            for operation, comparator in zip(node.ops, node.comparators):
                right = self._expression(comparator, local)
                comparisons = {
                    ast.Eq: left == right, ast.NotEq: left != right,
                    ast.Lt: left < right, ast.LtE: left <= right,
                    ast.Gt: left > right, ast.GtE: left >= right,
                }
                if not comparisons[type(operation)]:
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            branch = node.body if self._expression(node.test, local) else node.orelse
            return self._expression(branch, local)
        if isinstance(node, ast.Call):
            values = [self._expression(value, local) for value in node.args]
            return self._integer({"min": min, "max": max, "abs": abs}[node.func.id](*values))
        raise _RejectedCode("unsupported expression")

    def _statements(self, statements, local):
        for statement in statements:
            self._tick()
            if isinstance(statement, ast.Return):
                raise _Returned(self._expression(statement.value, local))
            if isinstance(statement, ast.Assign):
                local[statement.targets[0].id] = self._expression(statement.value, local)
            elif isinstance(statement, ast.If):
                branch = statement.body if self._expression(statement.test, local) else statement.orelse
                self._statements(branch, local)

    def __call__(self, values):
        self.steps = 0
        local = dict(zip(self.arguments, values))
        try:
            self._statements(self.body, local)
        except _Returned as result:
            if type(result.value) is not int:
                raise _RejectedCode("function must return an integer, not a boolean")
            return self._integer(result.value)
        raise _RejectedCode("function did not return an integer")


def _verify_code(world_id: str, candidate: dict, final: bool) -> tuple[bool, str]:
    if set(candidate) != {"code"}:
        return False, "Return exactly one code field containing the full function."
    task = _CODE[world_id]
    function = _IntegerFunction(candidate["code"], task["name"], task["arguments"])
    failed = []
    for name, arguments, expected in task["visible"]:
        actual = function(arguments)
        if actual != expected:
            failed.append(f"{name}: returned {actual}, expected {expected}")
    if failed:
        return False, "Visible tests failed: " + "; ".join(failed)
    if final and any(function(arguments) != expected for arguments, expected in task["hidden"]):
        return False, "Final verification complete."
    return True, "All visible tests passed. Hidden final checks have not been disclosed."


def _verify_evidence(world_id: str, step: int, candidate: dict) -> tuple[bool, str]:
    if set(candidate) != {"answer", "citations"}:
        return False, "Return exactly answer and citations."
    answer = candidate["answer"]
    if (
        type(answer) is not dict
        or set(answer) != {"lane", "max_units"}
        or type(answer["lane"]) is not str
        or type(answer["max_units"]) is not int
    ):
        return False, "answer requires exactly lane (string) and max_units (integer)."
    documents = _documents(world_id, step)
    citations = candidate["citations"]
    if (
        type(citations) is not list
        or len(citations) != 2
        or any(
            type(item) is not dict
            or set(item) != {"source_id", "version"}
            or type(item["source_id"]) is not str
            or type(item["version"]) is not int
            for item in citations
        )
        or {(item["source_id"], item["version"]) for item in citations}
        != {(doc["source_id"], doc["version"]) for doc in documents}
    ):
        return False, "Cite each current source exactly once using its source_id and version."
    policy, capacity = (doc["content"] for doc in documents)
    if world_id == "evidence_revision/dispatch_limit":
        lane = policy["selected_lane"]
        units = capacity[lane]
    else:
        lane = sorted(key for key, value in capacity.items() if value["state"] == policy["required_state"])[0]
        units = capacity[lane]["units"]
    correct = answer == {"lane": lane, "max_units": min(policy["request_limit"], units)}
    if not correct:
        return False, "The answer does not satisfy the current cross-document constraints."
    return True, "Current source versions and cross-document constraints verified."


def verify(world_id: str, step: int, text: str, *, final: bool = False) -> dict:
    """Check a proposed artifact without granting execution/publication authority.

    Public code verification runs visible cases only; final verification also
    runs hidden cases. Final calls always return generic feedback and no
    artifact, so callers cannot use hidden-test details as a correction oracle.
    """
    _identity(world_id, step)
    if type(final) is not bool:
        raise ValueError("final must be a boolean")
    candidate = None
    try:
        candidate = _candidate(text)
        if world_id in _CODE:
            valid, feedback = _verify_code(world_id, candidate, final)
        else:
            valid, feedback = _verify_evidence(world_id, step, candidate)
    except (ValueError, TypeError, RecursionError, OverflowError, ZeroDivisionError) as exc:
        valid = False
        # JSON parse errors may quote user text, but never fixture/hidden data.
        feedback = "Invalid candidate: " + str(exc)
    if final:
        return {"valid": valid, "feedback": "Final verification complete.", "artifact": None}
    artifact = None
    if valid:
        artifact = {
            "data_version": DATA_VERSION,
            "world_id": world_id,
            "task_version": 1 if world_id in _CODE or step < 2 else 2,
            "candidate": candidate,
            "verification": "visible_checks_only" if world_id in _CODE else "current_sources_checked",
        }
    return {"valid": valid, "feedback": feedback, "artifact": artifact}
