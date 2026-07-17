from pheroos.kernel import RuntimeScope


def test_runtime_scope_is_deterministic_and_tenant_isolated() -> None:
    first = RuntimeScope(
        tenant_id="tenant-a",
        run_id="run-1",
        request_id="request-1",
    )
    retry = RuntimeScope(
        tenant_id="tenant-a",
        run_id="run-1",
        request_id="request-2",
    )
    other_tenant = RuntimeScope(
        tenant_id="tenant-b",
        run_id="run-1",
        request_id="request-1",
    )

    assert first.scope_ref == retry.scope_ref
    assert first.scope_ref.startswith("sha256:")
    assert other_tenant.scope_ref != first.scope_ref


def test_runtime_scope_rejects_forged_scope_ref() -> None:
    try:
        RuntimeScope(
            tenant_id="tenant-a",
            run_id="run-1",
            request_id="request-1",
            scope_ref="sha256:" + "0" * 64,
        )
    except ValueError as exc:
        assert "scope_ref" in str(exc)
    else:  # pragma: no cover - explicit fail keeps the test dependency-free
        raise AssertionError("forged runtime scope ref was accepted")
