import pytest

from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable

NO_FX = FxTable(per_usd={"USD": 1.0, "CAD": None, "EUR": None})


def run(fx=NO_FX, **overrides):
    return evaluate(ProjectSpec.model_validate(overrides), fx=fx)


def arch(result, arch_id):
    return next(r for r in result.ranking if r.id == arch_id)


def test_no_hourly_rate_means_no_maintenance_cost():
    for item in run().ranking:
        assert item.maintenance_cost_monthly is None
        assert item.total_low_with_maintenance is None


def test_maintenance_cost_is_hours_times_rate_in_usd():
    result = run(team={"hourly_rate": 50})
    assert arch(result, "hetzner_vps").maintenance_cost_monthly == pytest.approx(300.0)  # 6 h
    assert arch(result, "gcp_cloud_run_sql").maintenance_cost_monthly == pytest.approx(100.0)  # 2 h


def test_total_with_maintenance_adds_the_maintenance():
    result = run(team={"hourly_rate": 50})
    hetzner = arch(result, "hetzner_vps")
    assert hetzner.total_low_with_maintenance == pytest.approx(hetzner.cost_low + 300.0, abs=0.01)
    assert hetzner.total_high_with_maintenance == pytest.approx(hetzner.cost_high + 300.0, abs=0.01)


def test_hourly_rate_in_cad_is_converted_with_exchange_rate():
    fx = FxTable(per_usd={"USD": 1.0, "CAD": 2.0}, as_of="2026-10-30")
    result = run(fx=fx, constraints={"budget_currency": "CAD"}, team={"hourly_rate": 100})
    hetzner = arch(result, "hetzner_vps")
    assert hetzner.maintenance_cost_monthly == pytest.approx(300.0)  # 100 CAD/h = 50 USD/h
    assert hetzner.maintenance_cost_display == pytest.approx(600.0)


def test_hourly_rate_without_exchange_rate_is_ignored_with_warning():
    result = run(constraints={"budget_currency": "CAD"}, team={"hourly_rate": 100})
    assert all(item.maintenance_cost_monthly is None for item in result.ranking)
    assert any("tarif horaire est ignoré" in w for w in result.global_warnings)


def test_warning_when_cheapest_hosting_is_not_cheapest_with_maintenance():
    result = run(team={"hourly_rate": 1000})
    assert any("n'est pas le moins cher avec la maintenance" in w for w in result.global_warnings)


def test_missing_information_warning():
    result = run()
    assert any("informations obligatoires manquent" in w for w in result.global_warnings)


def test_unknown_answers_warning():
    result = run(unknown=["traffic.daily_users"])
    assert any("je ne sais pas" in w for w in result.global_warnings)