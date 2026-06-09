from pheroos.governance import StopSignal, resolve_stop_signal


def test_stop_signal_blocks_target_action() -> None:
    resolution = resolve_stop_signal(StopSignal(target="decision:review", action="publish", reason="missing evidence"))

    assert resolution.blocked is True
    assert resolution.target == "decision:review"
