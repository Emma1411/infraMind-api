from models.evaluation import Verdict
from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable, get_fx

NO_FX = FxTable(per_usd={"USD": 1.0, "CAD": None, "EUR": None})


def run(fx=NO_FX, **overrides):
    spec = ProjectSpec.model_validate(overrides)
    return evaluate(spec, fx=fx)


def test_five_architectures_and_one_recommendation():
    result = run()
    assert len(result.ranking) == 5
    assert [r.verdict for r in result.ranking].count(Verdict.recommended) == 1
    assert result.recommended_id == result.ranking[0].id


def test_ranking_is_sorted_by_score():
    result = run()
    scores = [r.total_score for r in result.ranking]
    assert scores == sorted(scores, reverse=True)


def test_cost_range_is_ordered_and_priced():
    for item in run().ranking:
        assert item.cost_low > 0
        assert item.cost_high >= item.cost_low


def test_tiny_budget_eliminates_everything_and_recommends_nothing():
    result = run(constraints={"budget_max_monthly": 5, "budget_currency": "USD"})
    assert all(r.verdict == Verdict.eliminated for r in result.ranking)
    assert result.recommended_id is None
    assert all(r.eliminated_reasons for r in result.ranking)


def test_generous_budget_eliminates_nothing():
    result = run(constraints={"budget_max_monthly": 10000, "budget_currency": "USD"})
    assert all(r.verdict != Verdict.eliminated for r in result.ranking)


def test_budget_without_exchange_rate_does_not_eliminate_and_warns():
    result = run(constraints={"budget_max_monthly": 5, "budget_currency": "CAD"})
    assert all(r.verdict != Verdict.eliminated for r in result.ranking)
    assert any("Taux de change" in w for w in result.global_warnings)


def test_budget_in_cad_uses_exchange_rate():
    fx = FxTable(per_usd={"USD": 1.0, "CAD": 2.0}, as_of="2026-10-30")
    result = run(fx=fx, constraints={"budget_max_monthly": 40, "budget_currency": "CAD"})
    assert all(r.verdict == Verdict.eliminated for r in result.ranking)
    assert result.display_currency == "CAD"
    assert result.ranking[0].cost_low_display == round(result.ranking[0].cost_low * 2.0, 2)


def test_missing_budget_warns_and_eliminates_nothing():
    result = run()
    assert any("Budget mensuel non précisé" in w for w in result.global_warnings)
    assert all(r.verdict != Verdict.eliminated for r in result.ranking)


def test_imposed_provider_eliminates_the_others():
    result = run(constraints={"imposed_provider": "AWS"})
    for item in result.ranking:
        if item.provider == "aws":
            assert item.verdict != Verdict.eliminated
        else:
            assert item.verdict == Verdict.eliminated
    assert result.ranking[0].provider == "aws"


def test_unknown_imposed_provider_warns_without_eliminating():
    result = run(constraints={"imposed_provider": "OVH"})
    assert all(r.verdict != Verdict.eliminated for r in result.ranking)
    assert any("OVH" in w for w in result.global_warnings)


def test_always_on_flags_single_server_as_unmet():
    result = run(availability={"availability_target": "always_on"})
    hetzner = next(r for r in result.ranking if r.id == "hetzner_vps")
    assert hetzner.requirements_unmet


def test_low_data_loss_flags_daily_backups():
    result = run(backups={"acceptable_data_loss": "minutes"})
    hetzner = next(r for r in result.ranking if r.id == "hetzner_vps")
    assert any("sauvegardes quotidiennes" in u for u in hetzner.requirements_unmet)
    gcp = next(r for r in result.ranking if r.id == "gcp_cloud_run_sql")
    assert not gcp.requirements_unmet


def test_beginner_ops_flags_server_administration():
    result = run(team={"ops_skill": "none"})
    hetzner = next(r for r in result.ranking if r.id == "hetzner_vps")
    assert any("Administration de serveur" in u for u in hetzner.requirements_unmet)


def test_every_result_carries_region_scope_and_price_date():
    for item in run().ranking:
        assert "Amérique du Nord" in item.price_basis
    assert "région technique" in run().pricing_disclaimer


def test_assumptions_are_exposed():
    result = run()
    assert result.assumptions
    assert result.tier == "s"


def test_peaks_raise_the_tier():
    result = run(traffic={"daily_users": "between_100_1000", "has_peaks": True})
    assert result.tier == "m"


def test_multiple_environments_add_a_warning():
    result = run(delivery={"environments": ["dev", "prod"]})
    assert any("environnements demandés" in w for w in result.global_warnings)


def test_real_fx_file_loads():
    assert get_fx().rate("USD") == 1.0

def next_arch(result, arch_id):
    return next(r for r in result.ranking if r.id == arch_id)


def test_budget_risk_possible_when_next_tier_exceeds_budget():
    result = run(
        constraints={"budget_max_monthly": 150, "budget_currency": "USD"},
        traffic={"daily_users": "between_100_1000"},
    )
    gcp = next_arch(result, "gcp_cloud_run_sql")
    assert gcp.within_budget_low is True
    assert gcp.within_budget_high is False
    assert gcp.budget_risk.value == "possible"
    assert any("n'est pas garanti" in w for w in gcp.warnings)


def test_budget_risk_none_when_cost_stays_under_budget():
    result = run(
        constraints={"budget_max_monthly": 150, "budget_currency": "USD"},
        traffic={"daily_users": "between_100_1000"},
    )
    assert next_arch(result, "hetzner_vps").budget_risk.value == "none"


def test_budget_fields_are_none_without_budget():
    for item in run().ranking:
        assert item.within_budget_low is None
        assert item.budget_risk is None


def test_recommended_with_budget_risk_adds_global_warning():
    result = run(
        constraints={"budget_max_monthly": 150, "budget_currency": "USD", "imposed_provider": "Google"},
        traffic={"daily_users": "between_100_1000"},
    )
    assert result.recommended_id == "gcp_cloud_run_sql"
    assert any("n'est pas garanti" in w for w in result.global_warnings)


def test_availability_is_split_between_application_and_database():
    ec2 = next_arch(run(), "aws_ec2_rds")
    assert ec2.availability.application_score == 2
    assert ec2.availability.database_score == 3
    assert ec2.availability.overall_score == 2


def test_overall_availability_is_the_weakest_link():
    for item in run().ranking:
        a = item.availability
        assert a.overall_score == min(a.application_score, a.database_score)


def test_no_database_ignores_database_availability():
    result = run(data={"database_type": "none"})
    for item in result.ranking:
        assert item.availability.database_score is None
        assert item.availability.overall_score == item.availability.application_score


def test_availability_criterion_uses_overall_score():
    for item in run().ranking:
        criterion = next(s for s in item.scores if s.criterion == "availability")
        assert criterion.score == item.availability.overall_score * 20


def test_always_on_flags_single_ec2_but_not_cloud_run():
    result = run(availability={"availability_target": "always_on"})
    assert next_arch(result, "aws_ec2_rds").requirements_unmet
    assert not next_arch(result, "gcp_cloud_run_sql").requirements_unmet