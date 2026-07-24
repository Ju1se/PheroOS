"""Independent stdlib stores used only by the external integration fixture."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json

from pheroos.drivers import (
    DRIVER_INVOCATION_STORE_VERSION_V2,
    DriverInvocationReceiptV2,
    DriverInvocationRequestV2,
    DriverInvocationResultV2,
    DriverInvocationStoreErrorV2,
    DriverInvocationStoreV2,
)
from pheroos.trace import (
    SCOPED_TRACE_CURSOR_VERSION_V2,
    SCOPED_TRACE_STORE_VERSION_V2,
    ScopedTraceAppendReceiptV2,
    ScopedTraceCheckpointV2,
    ScopedTraceCursorV2,
    ScopedTraceEvent,
    ScopedTraceRecordV2,
    ScopedTraceRetirementV2,
    ScopedTraceStoreV2,
)


def _bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _digest(payload: dict[str, object]) -> str:
    return "sha256:" + sha256(_bytes(payload)).hexdigest()


class IndependentDriverStoreV2:
    """A non-reference Driver receipt store with its own checkpoint format."""

    store_version = DRIVER_INVOCATION_STORE_VERSION_V2

    def __init__(self, checkpoint: bytes | None = None) -> None:
        self._receipts: dict[tuple[str, str, str], DriverInvocationReceiptV2] = {}
        self._retired: set[str] = set()
        if checkpoint is not None:
            self._restore(checkpoint)

    @staticmethod
    def _key(receipt: DriverInvocationReceiptV2) -> tuple[str, str, str]:
        return receipt.scope_ref, receipt.driver_id, receipt.idempotency_key

    def record(
        self,
        request: DriverInvocationRequestV2,
        result: DriverInvocationResultV2,
    ) -> DriverInvocationReceiptV2:
        request_binding = tuple(
            getattr(request, field)
            for field in (
                "scope_ref",
                "driver_id",
                "invocation_id",
                "operation",
                "capability",
                "idempotency_key",
                "request_digest",
            )
        )
        result_binding = tuple(
            getattr(result, field)
            for field in (
                "scope_ref",
                "driver_id",
                "invocation_id",
                "operation",
                "capability",
                "idempotency_key",
                "request_digest",
            )
        )
        if request_binding != result_binding:
            raise DriverInvocationStoreErrorV2("independent Driver binding mismatch")
        receipt = DriverInvocationReceiptV2.for_result(result)
        key = self._key(receipt)
        if receipt.scope_ref in self._retired:
            raise DriverInvocationStoreErrorV2("independent Driver scope is retired")
        existing = self._receipts.get(key)
        if existing is not None:
            if existing != receipt:
                raise DriverInvocationStoreErrorV2(
                    "independent Driver idempotency conflict"
                )
            return existing
        self._receipts[key] = receipt
        return receipt

    def get(
        self,
        scope_ref: str,
        driver_id: str,
        idempotency_key: str,
    ) -> DriverInvocationReceiptV2 | None:
        if scope_ref in self._retired:
            return None
        return self._receipts.get((scope_ref, driver_id, idempotency_key))

    def retire(self, scope_ref: str) -> int:
        if scope_ref in self._retired:
            return 0
        keys = tuple(key for key in self._receipts if key[0] == scope_ref)
        for key in keys:
            del self._receipts[key]
        self._retired.add(scope_ref)
        return len(keys)

    def checkpoint(self) -> bytes:
        unsigned = {
            "checkpoint_version": "external-independent-driver-checkpoint-v1",
            "receipts": [
                item.to_dict()
                for item in sorted(self._receipts.values(), key=self._key)
            ],
            "retired_scopes": sorted(self._retired),
            "store_version": self.store_version,
        }
        return _bytes({**unsigned, "checkpoint_digest": _digest(unsigned)})

    @classmethod
    def restart(cls, checkpoint: bytes) -> IndependentDriverStoreV2:
        return cls(checkpoint)

    def _restore(self, checkpoint: bytes) -> None:
        try:
            payload = json.loads(checkpoint.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DriverInvocationStoreErrorV2(
                "independent Driver checkpoint is invalid"
            ) from exc
        fields = {
            "checkpoint_version",
            "receipts",
            "retired_scopes",
            "store_version",
            "checkpoint_digest",
        }
        if (
            type(payload) is not dict
            or set(payload) != fields
            or _bytes(payload) != checkpoint
        ):
            raise DriverInvocationStoreErrorV2(
                "independent Driver checkpoint fields are invalid"
            )
        digest = payload.pop("checkpoint_digest")
        if (
            payload["checkpoint_version"] != "external-independent-driver-checkpoint-v1"
            or payload["store_version"] != self.store_version
            or digest != _digest(payload)
            or type(payload["receipts"]) is not list
            or type(payload["retired_scopes"]) is not list
        ):
            raise DriverInvocationStoreErrorV2(
                "independent Driver checkpoint is inconsistent"
            )
        receipts = tuple(
            DriverInvocationReceiptV2.from_dict(item) for item in payload["receipts"]
        )
        keys = tuple(self._key(item) for item in receipts)
        if len(keys) != len(set(keys)):
            raise DriverInvocationStoreErrorV2(
                "independent Driver checkpoint has duplicate receipts"
            )
        self._receipts = dict(zip(keys, receipts, strict=True))
        self._retired = set(payload["retired_scopes"])


class IndependentTraceStoreV2:
    """Independent append/restart projection using only public Trace records."""

    store_version = SCOPED_TRACE_STORE_VERSION_V2

    def __init__(self, checkpoint: ScopedTraceCheckpointV2 | None = None) -> None:
        self._records: dict[tuple[str, str], list[ScopedTraceRecordV2]] = {}
        self._identities: dict[tuple[str, str, str, str], ScopedTraceRecordV2] = {}
        self._retirements: dict[str, ScopedTraceRetirementV2] = {}
        if checkpoint is not None:
            self._restore(checkpoint)

    def append_scoped_v2(
        self,
        event: ScopedTraceEvent,
    ) -> ScopedTraceAppendReceiptV2:
        canonical = ScopedTraceEvent.from_dict(event.to_dict())
        key = canonical.scope_ref, canonical.stream
        if canonical.scope_ref in self._retirements:
            raise ValueError("independent Trace scope is retired")
        matches = tuple(
            item
            for item in (
                self._identities.get((*key, "trace", canonical.trace_id)),
                self._identities.get((*key, "transition", canonical.transition_id)),
            )
            if item is not None
        )
        if matches:
            if (
                len({item.record_root for item in matches}) != 1
                or matches[0].event != canonical
            ):
                raise ValueError("independent Trace identity conflict")
            return ScopedTraceAppendReceiptV2("replayed", deepcopy(matches[0]))
        record = ScopedTraceRecordV2(
            canonical.scope_ref,
            canonical.stream,
            len(self._records.get(key, ())),
            canonical,
        )
        self._records.setdefault(key, []).append(record)
        self._index(record)
        return ScopedTraceAppendReceiptV2("appended", deepcopy(record))

    def snapshot_scoped_v2(
        self,
        scope_ref: str,
        stream: str,
        cursor: ScopedTraceCursorV2 | None = None,
    ) -> tuple[ScopedTraceRecordV2, ...]:
        values = self._records.get((scope_ref, stream), [])
        start = 0
        if cursor is not None:
            canonical = ScopedTraceCursorV2.from_dict(cursor.to_dict())
            if (
                canonical.scope_ref != scope_ref
                or canonical.stream != stream
                or canonical.next_sequence > len(values)
                or canonical.prefix_root
                != self._prefix(values[: canonical.next_sequence])
            ):
                raise ValueError("independent Trace cursor is stale")
            start = canonical.next_sequence
        return tuple(deepcopy(values[start:]))

    def cursor_scoped_v2(
        self,
        scope_ref: str,
        stream: str,
    ) -> ScopedTraceCursorV2:
        values = self._records.get((scope_ref, stream), [])
        return ScopedTraceCursorV2(
            scope_ref,
            stream,
            len(values),
            self._prefix(values),
        )

    def retire_scope_v2(self, scope_ref: str) -> ScopedTraceRetirementV2:
        existing = self._retirements.get(scope_ref)
        if existing is not None:
            return deepcopy(existing)
        records = [
            record.to_dict()
            for key in sorted(self._records)
            if key[0] == scope_ref
            for record in self._records[key]
        ]
        retirement = ScopedTraceRetirementV2(
            scope_ref,
            _digest(
                {
                    "records": records,
                    "scope_ref": scope_ref,
                    "version": self.store_version,
                }
            ),
        )
        self._retirements[scope_ref] = retirement
        return deepcopy(retirement)

    def checkpoint_v2(self) -> ScopedTraceCheckpointV2:
        return ScopedTraceCheckpointV2(
            tuple(
                record for key in sorted(self._records) for record in self._records[key]
            ),
            tuple(
                self._retirements[scope_ref] for scope_ref in sorted(self._retirements)
            ),
        )

    def restart_v2(
        self,
        checkpoint: ScopedTraceCheckpointV2,
    ) -> ScopedTraceStoreV2:
        return IndependentTraceStoreV2(checkpoint)

    @staticmethod
    def _prefix(records: list[ScopedTraceRecordV2]) -> str:
        return _digest(
            {
                "record_roots": [item.record_root for item in records],
                "version": SCOPED_TRACE_CURSOR_VERSION_V2,
            }
        )

    def _index(self, record: ScopedTraceRecordV2) -> None:
        base = record.scope_ref, record.stream
        for kind, identity in (
            ("trace", record.event.trace_id),
            ("transition", record.event.transition_id),
        ):
            key = (*base, kind, identity)
            if key in self._identities:
                raise ValueError("independent Trace checkpoint identity conflict")
            self._identities[key] = record

    def _restore(self, checkpoint: ScopedTraceCheckpointV2) -> None:
        canonical = ScopedTraceCheckpointV2.from_dict(checkpoint.to_dict())
        for record in canonical.records:
            key = record.scope_ref, record.stream
            values = self._records.setdefault(key, [])
            if record.sequence != len(values):
                raise ValueError("independent Trace checkpoint has a gap")
            self._index(record)
            values.append(record)
        self._retirements = {item.scope_ref: item for item in canonical.retirements}


assert isinstance(IndependentDriverStoreV2(), DriverInvocationStoreV2)
assert isinstance(IndependentTraceStoreV2(), ScopedTraceStoreV2)
