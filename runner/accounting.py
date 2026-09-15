"""MoneyLedger extracted byte-for-byte in behavior from remote_kimi_v1.py (MIT).

Historical schema, tariff, conservative reservations and settlement are retained.
One shared ledger remains the sole monetary owner. Opening cannot reset limits.
"""

from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
import sqlite3


BASE_URL = "https://api.moonshot.cn/v1"
MODEL = "kimi-k2.6"
INPUT_UPPER_BOUND = 262144
MAX_OUTPUT_TOKENS = 1024
# One accounting unit is 0.0000001 CNY: exact integer rates, no float rounding.
CNY_UNITS = 10_000_000
INPUT_RATE, CACHED_RATE, OUTPUT_RATE = 65, 11, 270
PRICE_VERSION = "kimi-cn-k2.6-cny-2026-09-14-v1"


class RemoteKimiError(RuntimeError):
    """A fixed, credential-free error code; never a provider response body."""


class BudgetExceeded(RemoteKimiError):
    pass


class DuplicateCall(RemoteKimiError):
    pass


def _integer(value, name, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f"invalid {name}")
    return value


def _wire(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False)


def _cny(units):
    return format(Decimal(units) / CNY_UNITS, ".7f")


class MoneyLedger:
    """One SQLite file shared by every activity using this authorization budget.

    Reservations are durable before HTTP dispatch. Pending/unknown calls retain
    their full charge and request slot after process death. IDs are never reused.
    Opening a ledger with different limits is rejected, including higher limits.
    """

    def __init__(self, path, *, budget_cny="50", max_http_requests=500):
        try:
            amount = Decimal(str(budget_cny)) * CNY_UNITS
            if not amount.is_finite() or amount != amount.to_integral_value():
                raise ValueError("invalid budget")
            self.budget_units = int(amount)
        except (InvalidOperation, ValueError, TypeError):
            raise ValueError("invalid budget") from None
        if not 0 < self.budget_units <= 50 * CNY_UNITS:
            raise ValueError("budget must be positive and at most CNY 50")
        _integer(max_http_requests, "request cap", 500)
        if not max_http_requests:
            raise ValueError("positive request cap required")
        self.max_http_requests = max_http_requests
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as db:
            db.execute("CREATE TABLE IF NOT EXISTS money_config (id INTEGER PRIMARY KEY, "
                       "budget INTEGER NOT NULL, request_cap INTEGER NOT NULL, price TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS money_calls (id TEXT PRIMARY KEY, "
                       "kind TEXT NOT NULL, state TEXT NOT NULL, reserved INTEGER NOT NULL, "
                       "actual INTEGER, prompt_bound INTEGER NOT NULL, output_bound INTEGER NOT NULL, "
                       "receipt TEXT, error TEXT, http_status INTEGER)")
            # A control-only probe ledger may predate HTTP-status diagnostics.
            columns = {row[1] for row in db.execute("PRAGMA table_info(money_calls)")}
            if "http_status" not in columns:
                db.execute("ALTER TABLE money_calls ADD COLUMN http_status INTEGER")
            db.execute("INSERT OR IGNORE INTO money_config VALUES (1,?,?,?)",
                       (self.budget_units, max_http_requests, PRICE_VERSION))
            row = db.execute("SELECT budget,request_cap,price FROM money_config WHERE id=1").fetchone()
            if tuple(row) != (self.budget_units, max_http_requests, PRICE_VERSION):
                raise ValueError("ledger limits or price version differ")

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, call_id, *, prompt_bound, output_bound, kind="generation"):
        if (type(call_id) is not str or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,240}", call_id)
                or kind not in {"generation", "models"}):
            raise ValueError("invalid call identity")
        _integer(prompt_bound, "prompt bound", INPUT_UPPER_BOUND)
        _integer(output_bound, "output bound", MAX_OUTPUT_TOKENS)
        if ((kind == "generation" and (prompt_bound != INPUT_UPPER_BOUND or output_bound < 1))
                or (kind == "models" and (prompt_bound or output_bound))):
            raise ValueError("invalid reservation bounds")
        reserved = prompt_bound * INPUT_RATE + output_bound * OUTPUT_RATE
        with self._transaction() as db:
            if db.execute("SELECT 1 FROM money_calls WHERE id=?", (call_id,)).fetchone():
                raise DuplicateCall("call_id_already_reserved")
            count, held = db.execute("SELECT COUNT(*),COALESCE(SUM(COALESCE(actual,reserved)),0) "
                                     "FROM money_calls").fetchone()
            if count >= self.max_http_requests or held + reserved > self.budget_units:
                raise BudgetExceeded("request_or_money_cap_exceeded")
            db.execute("INSERT INTO money_calls "
                       "(id,kind,state,reserved,prompt_bound,output_bound) VALUES (?,?,?,?,?,?)",
                       (call_id, kind, "reserved", reserved, prompt_bound, output_bound))

    def settle(self, call_id, receipt):
        """Settle only validated usage, retaining upper pricing when cache is absent."""
        with self._transaction() as db:
            row = db.execute("SELECT * FROM money_calls WHERE id=?", (call_id,)).fetchone()
            if row is None or row["state"] != "reserved":
                raise ValueError("settlement requires a pending reservation")
            if row["kind"] == "generation":
                usage = receipt["usage"]
                prompt = _integer(usage["prompt_tokens"], "prompt usage", row["prompt_bound"])
                output = _integer(usage["completion_tokens"], "output usage", row["output_bound"])
                total = _integer(usage["total_tokens"], "total usage", INPUT_UPPER_BOUND)
                cached = _integer(usage.get("cached_tokens", 0), "cache usage", prompt)
                if total != prompt + output:
                    raise ValueError("inconsistent total usage")
                actual = (prompt - cached) * INPUT_RATE + cached * CACHED_RATE + output * OUTPUT_RATE
            else:
                actual = 0
            if actual > row["reserved"]:
                raise ValueError("usage exceeds money reservation")
            db.execute("UPDATE money_calls SET state='settled',actual=?,receipt=? WHERE id=?",
                       (actual, _wire(receipt), call_id))
        return _cny(actual)

    def unknown(self, call_id, error, *, http_status=None):
        # Error values come exclusively from this finite local vocabulary.
        if error not in {"timeout", "http_error", "transport_error", "invalid_response",
                         "response_too_large", "unexpected_failure"}:
            raise ValueError("unknown error code")
        if http_status is not None and (type(http_status) is not int or not 100 <= http_status <= 599):
            raise ValueError("invalid HTTP status")
        with self._transaction() as db:
            db.execute("UPDATE money_calls SET state='unknown',error=?,http_status=? "
                       "WHERE id=? AND state='reserved'", (error, http_status, call_id))

    def call(self, call_id):
        with self._transaction() as db:
            row = db.execute("SELECT * FROM money_calls WHERE id=?", (call_id,)).fetchone()
            if row is None:
                raise ValueError("unknown call")
            return {**dict(row), "receipt": json.loads(row["receipt"]) if row["receipt"] else None}

    def summary(self):
        with self._transaction() as db:
            rows = db.execute("SELECT state,reserved,actual FROM money_calls").fetchall()
        settled = sum(r["actual"] for r in rows if r["actual"] is not None)
        unresolved = sum(r["reserved"] for r in rows if r["actual"] is None)
        return {"price_version": PRICE_VERSION, "budget_cny": _cny(self.budget_units),
                "http_requests": len(rows), "max_http_requests": self.max_http_requests,
                "settled_cny": _cny(settled), "unresolved_reserved_cny": _cny(unresolved),
                "available_cny": _cny(self.budget_units - settled - unresolved),
                "unresolved_calls": sum(r["actual"] is None for r in rows)}

    snapshot = summary


