from __future__ import annotations

import json

import pytest

from pheroos_bench import e3_power


def test_synthetic_diagnostic_reproduces_and_declares_scope():
    first = e3_power.simulate(trials=2, resamples=9, seed=17)
    assert first == e3_power.simulate(trials=2, resamples=9, seed=17)
    assert first["llm_calls"] == 0
    assert first["inference"]["nominal_one_sided_alpha"] == 0.025
    assert first["status"] == "synthetic_diagnostic_not_confirmatory_evidence"
    assert len(first["scenarios"]) == 6
    assert first["scenarios"][0]["true_mean_quality_difference"] == 0
    assert first["scenarios"][2]["treatment_probability"] == 0.7
    for scenario in first["scenarios"]:
        for method in scenario["methods"].values():
            assert 0 <= method["detections"] <= 2
            assert method["detection_rate"] == method["detections"] / 2


@pytest.mark.parametrize(
    "kwargs",
    [
        {"trials": 0},
        {"trials": True},
        {"resamples": 1},
        {"resamples": 2.5},
        {"seed": -1},
        {"seed": False},
    ],
)
def test_invalid_diagnostic_configuration(kwargs):
    with pytest.raises(ValueError):
        e3_power.simulate(**kwargs)


@pytest.mark.parametrize("upper", [0.1, 0.1 + 5e-13])
def test_methods_receive_identical_item_differences_and_bootstrap_seeds(
    monkeypatch, upper
):
    calls = []

    def ci(differences, **kwargs):
        calls.append((list(differences), kwargs))
        return 0.1, upper

    monkeypatch.setattr(e3_power, "paired_percentile_ci", ci)
    report = e3_power.simulate(trials=1, resamples=9, seed=23)
    for median_call, mean_call in zip(calls[::2], calls[1::2], strict=True):
        assert median_call[0] == mean_call[0]
        assert median_call[1]["seed"] == mean_call[1]["seed"]
        assert median_call[1]["statistic"] == "median"
        assert mean_call[1]["statistic"] == "mean"
    for scenario in report["scenarios"]:
        assert scenario["methods"]["median"]["detections"] == 1
        assert scenario["methods"]["mean"]["detections"] == 0


def test_cli_writes_same_report(tmp_path):
    output = tmp_path / "diagnostic.json"
    assert (
        e3_power.main(
            [
                "--trials",
                "1",
                "--resamples",
                "9",
                "--seed",
                "7",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert json.loads(output.read_text()) == e3_power.simulate(
        trials=1, resamples=9, seed=7
    )
