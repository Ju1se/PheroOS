from pheroos.governance import RecoveryTrace


def test_recovery_trace_records_declared_selection_inputs() -> None:
    trace = RecoveryTrace(
        protocol_id="toy.review",
        trigger_target="decision:review",
        selected_roles=["reviewer"],
        selected_tags=["toy"],
        selected_tools=[],
        failure_candidate="candidate:insufficient_evidence",
    )

    assert trace.selected_roles == ["reviewer"]
    assert trace.failure_candidate == "candidate:insufficient_evidence"
