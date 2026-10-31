from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable

NO_FX = FxTable(per_usd={"USD": 1.0, "CAD": None, "EUR": None})


def run(**overrides):
    return evaluate(ProjectSpec.model_validate(overrides), fx=NO_FX)


def entry(result, path):
    return next(e for e in result.sensitivity if e.path == path)


def test_five_fields_sorted_by_spread():
    result = run()
    assert len(result.sensitivity) == 5
    spreads = [e.spread for e in result.sensitivity]
    assert spreads == sorted(spreads, reverse=True)


def test_traffic_covers_all_bands_and_cost_grows():
    traffic = entry(run(), "traffic.daily_users")
    assert [s.value for s in traffic.scenarios] == [
        "under_100",
        "between_100_1000",
        "between_1000_10000",
        "over_10000",
    ]
    assert traffic.cost_max > traffic.cost_min


def test_known_field_has_exactly_one_current_scenario():
    result = run(traffic={"daily_users": "between_1000_10000"})
    traffic = entry(result, "traffic.daily_users")
    assert traffic.status == "known"
    current = [s for s in traffic.scenarios if s.is_current]
    assert len(current) == 1
    assert current[0].value == "between_1000_10000"


def test_missing_field_is_marked_assumed():
    assert entry(run(), "traffic.has_peaks").status == "assumed"


def test_assumed_value_matches_the_engine_default():
    result = run()
    assert entry(result, "traffic.has_peaks").current_label == "Non"
    assert entry(result, "traffic.daily_users").current_label == "100 à 1 000"


def test_sensitivity_is_not_recursive():
    spec = ProjectSpec()
    assert evaluate(spec, fx=NO_FX, with_sensitivity=False).sensitivity == []


def test_sensitivity_follows_the_recommended_architecture():
    result = run()
    assert all(e.arch_id == result.recommended_id for e in result.sensitivity)


def test_change_flag_matches_scenarios():
    result = run()
    for e in result.sensitivity:
        expected = any(s.recommended_id != result.recommended_id for s in e.scenarios)
        assert e.changes_recommendation == expected