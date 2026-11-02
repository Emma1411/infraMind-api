from datetime import date

import pytest
from fastapi.testclient import TestClient

from main import app
from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable
from services.export.quote import (
    NoRecommendation,
    UnknownQuoteArchitecture,
    build_quote,
    escape,
    money,
)
from services.questions.bank import QUESTION_BANK

NO_FX = FxTable(per_usd={"USD": 1.0, "CAD": None, "EUR": None})
TODAY = date(2026, 11, 1)
SPEC = {
    "name": "Salon Élégance",
    "traffic": {"daily_users": "between_100_1000"},
    "data": {"data_size": "gb_1_10"},
}

client = TestClient(app)


def make(**extra) -> ProjectSpec:
    return ProjectSpec.model_validate({**SPEC, **extra})


def quote(spec=None, **kwargs):
    kwargs.setdefault("fx", NO_FX)
    kwargs.setdefault("today", TODAY)
    return build_quote(spec or make(), **kwargs)


def arch_of(spec, arch_id=None):
    result = evaluate(spec, fx=NO_FX)
    return result, next(r for r in result.ranking if r.id == (arch_id or result.recommended_id))


def test_quote_contains_every_section():
    md = quote().markdown
    for heading in (
        "# Section « Infrastructure » du devis",
        "## 1. Recommandation",
        "## 2. Coûts récurrents (par mois)",
        "## 3. Maintenance",
        "## 4. Coûts ponctuels à prévoir",
        "## 5. Comment facturer l'hébergement",
        "## 6. Hypothèses retenues",
        "## 7. Points à confirmer avec le client",
        "## 8. Ce qui peut faire varier le prix",
        "## 9. Risques et limites",
        "## 10. Alternatives étudiées",
        "## Base des prix et avertissement",
    ):
        assert heading in md, heading


def test_default_architecture_is_the_recommended_one():
    spec = make()
    result, arch = arch_of(spec)
    response = quote(spec)
    assert response.arch_id == result.recommended_id
    assert arch.label in response.markdown
    assert "architecture recommandée par l'analyse" in response.markdown


def test_cost_range_is_shown_with_both_bounds():
    spec = make()
    _, arch = arch_of(spec)
    md = quote(spec).markdown
    assert f"de {money(arch.cost_low)} à {money(arch.cost_high)} par mois" in md


def test_dates_and_validity():
    response = quote()
    assert response.generated_on == "2026-11-01"
    assert response.valid_until == "2026-12-01"
    assert "**Date de l'estimation :** 2026-11-01" in response.markdown
    assert "**Estimation valable jusqu'au :** 2026-12-01" in response.markdown


def test_custom_validity_changes_the_end_date():
    assert quote(validity_days=60).valid_until == "2026-12-31"


def test_filename_uses_project_name_and_date():
    assert quote().filename == "devis-infrastructure-salon-elegance-2026-11-01.md"
    assert quote(ProjectSpec()).filename == "devis-infrastructure-mon-application-2026-11-01.md"


def test_recurring_costs_list_every_cost_line_and_the_total():
    spec = make()
    _, arch = arch_of(spec)
    md = quote(spec).markdown
    for line in arch.lines:
        assert escape(line.label) in md
    assert f"**{money(arch.cost_low)}**" in md


def test_maintenance_without_hourly_rate_says_so():
    assert "Tarif horaire non renseigné" in quote().markdown


def test_maintenance_with_hourly_rate_gives_an_amount():
    spec = make(team={"hourly_rate": 50})
    _, arch = arch_of(spec)
    md = quote(spec).markdown
    assert money(arch.maintenance_hours_per_month * 50) in md
    assert "Tarif horaire non renseigné" not in md


def test_flat_fee_uses_the_high_bound_and_the_margin():
    spec = make()
    _, arch = arch_of(spec)
    md = quote(spec, margin_percent=10).markdown
    assert money(arch.cost_high * 1.10) in md
    assert "une marge de 10 %" in md


def test_missing_information_becomes_questions_for_the_client():
    md = quote(ProjectSpec()).markdown
    assert QUESTION_BANK["traffic.daily_users"].text in md
    assert "Informations manquantes" in md


def test_unknown_answers_are_listed():
    md = quote(make(unknown=["traffic.has_peaks"])).markdown
    assert "« je ne sais pas »" in md
    assert QUESTION_BANK["traffic.has_peaks"].text in md


def test_sensitivity_is_shown_for_the_recommended_architecture():
    spec = make()
    result = evaluate(spec, fx=NO_FX)
    md = quote(spec).markdown
    assert any(entry.question in md for entry in result.sensitivity[:3])


def test_sensitivity_is_omitted_for_another_architecture():
    spec = make()
    result = evaluate(spec, fx=NO_FX)
    other = next(r.id for r in result.ranking if r.id != result.recommended_id)
    md = quote(spec, arch_id=other).markdown
    assert "La sensibilité n'est calculée que pour l'architecture recommandée" in md
    assert "Architecture choisie manuellement" in md


def test_alternatives_can_be_left_out():
    md = quote(include_alternatives=False).markdown
    assert "## 10. Alternatives étudiées" not in md
    assert "## Base des prix et avertissement" in md


def test_chosen_eliminated_architecture_is_flagged():
    spec = make(constraints={"budget_max_monthly": 5, "budget_currency": "USD"})
    md = quote(spec, arch_id="hetzner_vps").markdown
    assert "cette architecture est éliminée" in md
    assert "Éliminée :" in md


def test_no_recommendation_raises():
    spec = make(constraints={"budget_max_monthly": 5, "budget_currency": "USD"})
    with pytest.raises(NoRecommendation):
        quote(spec)


def test_unknown_architecture_raises():
    with pytest.raises(UnknownQuoteArchitecture):
        quote(arch_id="inexistante")


def test_escape_protects_tables():
    assert escape("a|b\nc") == "a\\|b c"
    assert escape("  deux   espaces ") == "deux espaces"


def test_money_format_is_french():
    assert money(1234.5) == "1 234,50 $ US"
    assert money(0) == "0,00 $ US"
    assert money(12.3, "$ CA") == "12,30 $ CA"


def test_second_currency_is_shown_when_a_rate_exists():
    fx = FxTable(per_usd={"USD": 1.0, "CAD": 2.0}, as_of="2026-10-30")
    spec = make(constraints={"budget_max_monthly": 10000, "budget_currency": "CAD"})
    md = quote(spec, fx=fx).markdown
    assert "≈" in md and "$ CA" in md


def test_disclaimer_and_price_basis_are_present():
    md = quote().markdown
    assert "Amérique du Nord" in md
    assert "région technique" in md
    assert "ne constituent pas un engagement" in md


def test_endpoint_returns_markdown():
    response = client.post("/api/export/quote", json={"spec": SPEC, "client_name": "Salon Élégance inc."})
    assert response.status_code == 200
    body = response.json()
    assert body["filename"].startswith("devis-infrastructure-salon-elegance-")
    assert "## 1. Recommandation" in body["markdown"]
    assert "**Client :** Salon Élégance inc." in body["markdown"]


def test_endpoint_unknown_architecture_is_404():
    response = client.post("/api/export/quote", json={"spec": SPEC, "arch_id": "inexistante"})
    assert response.status_code == 404


def test_endpoint_without_recommendation_is_422():
    spec = {"constraints": {"budget_max_monthly": 5, "budget_currency": "USD"}}
    assert client.post("/api/export/quote", json={"spec": spec}).status_code == 422


def test_endpoint_rejects_invalid_validity():
    assert client.post("/api/export/quote", json={"spec": SPEC, "validity_days": 0}).status_code == 422