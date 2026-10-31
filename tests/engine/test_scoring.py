import pytest

from models.project_spec import ProjectSpec
from services.engine.fx import FxFile
from services.engine.scoring import BASE_WEIGHTS, compute_weights, cost_score


def spec(**overrides) -> ProjectSpec:
    return ProjectSpec.model_validate(overrides)


def test_weights_sum_to_100():
    weights, _ = compute_weights(spec())
    assert sum(weights.values()) == pytest.approx(100, abs=0.5)


def test_default_weights_have_no_reasons():
    weights, reasons = compute_weights(spec())
    assert reasons == []
    assert set(weights) == set(BASE_WEIGHTS)


def test_beginner_ops_raises_maintenance_weight():
    base, _ = compute_weights(spec())
    weights, reasons = compute_weights(spec(team={"ops_skill": "none"}))
    assert weights["maintenance"] > base["maintenance"]
    assert reasons


def test_always_on_raises_availability_weight():
    base, _ = compute_weights(spec())
    weights, _ = compute_weights(spec(availability={"availability_target": "always_on"}))
    assert weights["availability"] > base["availability"]


def test_payment_data_raises_security_weight():
    base, _ = compute_weights(spec())
    weights, _ = compute_weights(spec(compliance={"payment_data": True}))
    assert weights["security"] > base["security"]


def test_cheapest_gets_full_cost_score():
    assert cost_score(40, 40) == 100.0
    assert cost_score(80, 40) == 50.0
    assert cost_score(0, 0) == 100.0


def test_fx_rate_requires_a_date():
    with pytest.raises(Exception):
        FxFile(as_of=None, per_usd={"USD": 1.0, "CAD": 1.4})
    assert FxFile(as_of="2026-10-30", per_usd={"USD": 1.0, "CAD": 1.4})