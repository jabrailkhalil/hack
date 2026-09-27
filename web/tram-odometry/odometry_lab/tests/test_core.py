from dataclasses import asdict
from types import SimpleNamespace
import numpy as np
import pytest
from tram_lab.types import Event, Estimate, FRONT, REAR, COMMAND, MASTER_VEL, ROVER_VEL
from tram_lab.estimators import WheelEstimator
from tram_lab.replay import replay, EventClock
from tram_lab.signals import align_reference, causal_derivative, integrate_velocity, convert_units, detect_segments
from tram_lab.adapters import event_from_message
from tram_lab.faults import inject_faults
from tram_lab.metrics import compute_metrics

BASE = 1_786_353_518_961_320_453


def wheel(topic=FRONT, offset=0, raw=36., seq=0, header_offset=None):
    return Event(topic, BASE + (offset if header_offset is None else header_offset), BASE + offset, seq, {"velocity": raw})


def gnss(topic=MASTER_VEL, offset=0, x=10, y=0, seq=50):
    return Event(topic, BASE + offset, BASE + offset, seq, {"x": x, "y": y, "z": 0.})


def test_nanosecond_math_and_units():
    t = np.array([BASE, BASE + 1, BASE + 2], dtype=np.int64)
    np.testing.assert_allclose(causal_derivative(t, [1., 2., 3.])[1:], [1e9, 1e9])
    np.testing.assert_allclose(integrate_velocity(t, [10., 10., 10.]), [0, 1e-8, 2e-8], atol=1e-20)
    np.testing.assert_allclose(convert_units([36, 72]), [10, 20])
    with pytest.raises(ValueError): integrate_velocity(t[::-1], [1, 1, 1])
    assert np.isnan(causal_derivative([1, 1, 0], [1, 2, 3])).all()


def test_nearest_reference_ties_tolerance_and_original_indices():
    ix, delta = align_reference([BASE + 50, BASE + 400, BASE + 201], [BASE + 200, BASE], 50)
    assert ix.tolist() == [1, -1, 0]
    assert delta.tolist() == [50, 200, 1]
    assert align_reference([BASE], [], 50)[0].tolist() == [-1]


@pytest.mark.parametrize("mode,expected", [("front", 10), ("rear", 20), ("mean", 15)])
def test_baselines_integrate_expected_speed(mode, expected):
    events = [wheel(seq=0), wheel(REAR, raw=72., seq=1)]
    estimates = list(replay(events, WheelEstimator({"name": mode}), BASE, BASE + 1_000_000_000))
    assert estimates[0].distance == 0
    assert estimates[-1].distance == pytest.approx(expected)
    assert estimates[-1].velocity == expected
    assert estimates[-1].status == "stale"


def test_initial_unavailability_and_nan_does_not_replace_valid_sample():
    events = [wheel(seq=0), wheel(REAR, offset=100_000_000, raw=72, seq=1), wheel(offset=150_000_000, raw=float("nan"), seq=2)]
    estimates = list(replay(events, WheelEstimator({"name": "mean"}), BASE, BASE + 200_000_000))
    assert [e.status for e in estimates[:2]] == ["unavailable", "unavailable"]
    assert estimates[2].distance == 0
    assert estimates[-1].velocity == 15
    assert estimates[-1].diagnostics["rejected_values"] == 1


def test_no_future_inputs_no_gnss_and_stable_tie_order():
    class Spy:
        def __init__(self): self.events = []
        def update(self, event):
            assert event.topic in (FRONT, REAR, COMMAND)
            self.events.append(event)
        def predict(self, t):
            assert all(e.received_ns <= t for e in self.events)
            return Estimate(t, None, None, "unavailable", {"seen": [e.sequence for e in self.events]})
    spy = Spy()
    events = [wheel(seq=0), gnss(offset=25_000_000), wheel(REAR, offset=50_000_000, seq=2), wheel(offset=50_000_000, seq=3)]
    estimates = list(replay(events, spy, BASE, BASE + 100_000_000))
    assert estimates[0].diagnostics["seen"] == [0]
    assert estimates[1].diagnostics["seen"] == [0, 2, 3]
    with pytest.raises(ValueError): WheelEstimator().update(gnss())


def test_header_rollback_does_not_reset_path_receipt_rollback_requires_reset():
    events = [wheel(seq=0), wheel(offset=100_000_000, header_offset=-1_000_000_000, seq=1)]
    estimator = WheelEstimator({"name": "front"})
    estimates = list(replay(events, estimator, BASE, BASE + 200_000_000))
    assert estimates[-1].distance == pytest.approx(2)
    assert estimates[-1].diagnostics["clock_anomalies"] == 1
    with pytest.raises(ValueError): estimator.predict(BASE)
    estimator.reset({"name": "front"})
    estimator.update(wheel())
    assert estimator.predict(BASE).distance == 0


def test_adapter_core_parity():
    original = [wheel(seq=0), wheel(REAR, offset=10_000_000, raw=72, seq=1), wheel(offset=100_000_000, raw=18, seq=2)]
    converted = []
    for e in original:
        sec, ns = divmod(e.stamp_ns, 10**9)
        msg = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=sec, nanosec=ns), frame_id=""), velocity=e.data["velocity"])
        converted.append(event_from_message(e.topic, msg, e.received_ns, e.sequence))
    a = list(replay(original, WheelEstimator(), BASE, BASE + 300_000_000))
    b = list(replay(converted, WheelEstimator(), BASE, BASE + 300_000_000))
    assert a == b
    command = SimpleNamespace(header=SimpleNamespace(stamp=SimpleNamespace(sec=1, nanosec=3), frame_id=""), position=-15)
    assert event_from_message(COMMAND, command, BASE, 10).data["position"] == -15


def test_faults_deterministic_and_gnss_untouched():
    events = [wheel(offset=i*100_000_000, raw=36+i, seq=i) for i in range(10)]
    reference = gnss(offset=50_000_000)
    events.insert(1, reference)
    faults = [{"kind": "spike", "probability": .5, "amplitude": 18}, {"kind": "delay", "start_s": .2, "end_s": .5, "delay_s": .2}]
    a = list(inject_faults(events, faults, 123, BASE))
    b = list(inject_faults(events, faults, 123, BASE))
    assert a == b
    assert next(e for e in a if e.topic == MASTER_VEL) is reference
    assert all(e.stamp_ns == next(x.stamp_ns for x in events if x.sequence == e.sequence) for e in a)
    assert [e.received_ns for e in a] == sorted(e.received_ns for e in a)
    with pytest.raises(ValueError): list(inject_faults(events, [{"kind": "drop", "topics": [MASTER_VEL]}]))


def test_drop_freeze_scale_boundaries():
    events = [wheel(offset=i*100_000_000, raw=36+i, seq=i) for i in range(5)]
    frozen = list(inject_faults(events, [{"kind": "freeze", "start_s": .1, "end_s": .3}], start_ns=BASE))
    assert [e.data["velocity"] for e in frozen] == [36, 36, 36, 39, 40]
    dropped = list(inject_faults(events, [{"kind": "drop", "start_s": .1, "end_s": .3}], start_ns=BASE))
    assert [e.sequence for e in dropped] == [0, 3, 4]
    scaled = list(inject_faults(events, [{"kind": "scale", "factor": 2}], start_ns=BASE))
    assert scaled[0].data["velocity"] == 72


def test_missing_reference_and_rover_fallback():
    estimates = [Estimate(BASE + i*50_000_000, 10, i*.5, "ok") for i in range(3)]
    missing = compute_metrics(estimates, [])
    assert missing["speed"]["rmse_mps"] is None
    assert missing["prediction_coverage"] == 1 and missing["coverage"] == 0
    refs = [gnss(ROVER_VEL, offset=i*50_000_000) for i in range(3)]
    metrics = compute_metrics(estimates, refs)
    assert metrics["reference"]["source"] == "rover"
    assert metrics["speed"]["rmse_mps"] == 0
    assert metrics["path"]["full_interval_end_error_m"] == 0


def test_no_silent_reference_repair_explicit_quality_mask():
    predictions = [Estimate(BASE, 10, 0, "ok"), Estimate(BASE + 50_000_000, 10, .5, "ok")]
    events = [gnss(x=0), gnss(ROVER_VEL, x=10), gnss(offset=50_000_000), gnss(ROVER_VEL, offset=50_000_000)]
    metrics = compute_metrics(predictions, events, quality={"max_receiver_disagreement_mps": .5})
    assert metrics["speed"]["rmse_mps"] == pytest.approx(np.sqrt(50))
    assert metrics["explicit_quality_mask"]["excluded"] == 1
    assert metrics["explicit_quality_mask"]["speed"]["rmse_mps"] == 0


def test_path_reference_gaps_not_bridged():
    estimates = [Estimate(BASE + i*50_000_000, 10, i*.5, "ok") for i in range(31)]
    refs = [gnss(offset=i*50_000_000) for i in [0, 1, 2, 28, 29, 30]]
    result = compute_metrics(estimates, refs)
    assert result["path"]["segments"] == 2
    assert result["path"]["full_interval_end_error_m"] is None
    assert result["path"]["covered_duration_s"] < .5


def test_intervals_and_empty_inputs():
    assert detect_segments([], []) == []
    assert [x["samples"] for x in detect_segments([1, 2, 3], ["stop", "go", "go"])] == [1, 2]
    assert compute_metrics([], [])["ticks"] == 0


def test_example_plugin_uses_filtered_velocity_for_its_own_distance():
    from tram_lab.estimators import make_estimator
    estimator = make_estimator({"factory": "tram_lab.example:ExponentialMeanEstimator", "time_constant_s": .1})
    events = [wheel(seq=0, raw=0), wheel(REAR, seq=1, raw=0),
              wheel(offset=100_000_000, seq=2), wheel(REAR, offset=100_000_000, seq=3)]
    estimates = list(replay(events, estimator, BASE, BASE + 200_000_000))
    assert 0 < estimates[-1].velocity < 10
    integrated = integrate_velocity([e.time_ns for e in estimates], [e.velocity for e in estimates])
    assert estimates[-1].distance == pytest.approx(integrated[-1])


def test_nonfinite_trace_is_strict_json_and_preserves_rejection_behavior():
    import json
    from tram_lab.adapters import trace_safe
    event = wheel(offset=50_000_000, raw=float("nan"), seq=1)
    recorded = Event(**json.loads(json.dumps(trace_safe(asdict(event)), allow_nan=False)))
    a = list(replay([wheel(), event], WheelEstimator({"name": "front"}), BASE, BASE+100_000_000))
    b = list(replay([wheel(), recorded], WheelEstimator({"name": "front"}), BASE, BASE+100_000_000))
    assert a == b and a[-1].diagnostics["rejected_values"] == 1
