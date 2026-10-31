from models.evaluation import (
    ArchitectureResult,
    AvailabilityDetail,
    BudgetRisk,
    CriterionScore,
    EvaluationResult,
    Verdict,
    WeightInfo,
)
from models.project_spec import (
    AvailabilityTarget,
    DatabaseType,
    LossTolerance,
    OpsSkill,
    ProjectSpec,
)
from services.engine.architectures import RATED_CRITERIA, SCORE_ORDER, ArchitectureDef, get_architectures
from services.engine.assumptions import TIER_LABELS, build_sizing, next_tier
from services.engine.catalog import PRICING_DISCLAIMER, Catalog, get_catalog
from services.engine.costing import BUILDERS
from services.engine.fx import FxTable, get_fx
from services.engine.scoring import compute_weights, cost_score
from services.engine.sensitivity import compute_sensitivity
from services.engine.graphs import build_graph

_PROVIDER_ALIASES = {
    "hetzner": "hetzner",
    "aws": "aws",
    "amazon": "aws",
    "azure": "azure",
    "microsoft": "azure",
    "gcp": "gcp",
    "google": "gcp",
}


def _budget_in_usd(spec: ProjectSpec, fx: FxTable) -> tuple[float | None, str | None]:
    amount = spec.constraints.budget_max_monthly
    currency = spec.constraints.budget_currency
    if amount is None:
        return None, "Budget mensuel non précisé : aucune architecture n'est éliminée sur le coût."
    if currency is None:
        return None, "Devise du budget non précisée : le budget ne peut pas être comparé."
    rate = fx.rate(currency.value)
    if rate is None:
        return None, (
            f"Taux de change {currency.value}/USD non renseigné : le budget ne peut pas être comparé. "
            "Renseigne-le dans data/fx.json."
        )
    return amount / rate, None


def _hourly_rate_usd(spec: ProjectSpec, fx: FxTable) -> tuple[float | None, str | None]:
    """Tarif horaire converti en USD. Exprimé dans la devise du budget, ou en USD si elle est absente."""
    rate = spec.team.hourly_rate
    if rate is None:
        return None, None
    currency = spec.constraints.budget_currency.value if spec.constraints.budget_currency else "USD"
    per_usd = fx.rate(currency)
    if per_usd is None:
        return None, (
            f"Taux de change {currency}/USD non renseigné : le tarif horaire est ignoré. "
            "Renseigne-le dans data/fx.json."
        )
    return rate / per_usd, None


def _budget_status(
    budget_usd: float | None, low: float, high: float
) -> tuple[bool | None, bool | None, BudgetRisk | None]:
    if budget_usd is None:
        return None, None, None
    within_low = low <= budget_usd
    within_high = high <= budget_usd
    if within_high:
        risk = BudgetRisk.none
    elif within_low:
        risk = BudgetRisk.possible
    else:
        risk = BudgetRisk.over
    return within_low, within_high, risk


def _imposed_provider(spec: ProjectSpec) -> tuple[str | None, str | None]:
    raw = spec.constraints.imposed_provider
    if not raw:
        return None, None
    text = raw.lower()
    for alias, provider in _PROVIDER_ALIASES.items():
        if alias in text:
            return provider, None
    return None, (
        f"Fournisseur imposé « {raw} » non couvert par le catalogue : "
        "aucune architecture n'est éliminée sur ce critère."
    )


def _availability(spec: ProjectSpec, arch: ArchitectureDef) -> AvailabilityDetail:
    app = arch.availability_app
    if spec.data.database_type == DatabaseType.none:
        return AvailabilityDetail(
            application_score=app.score,
            application_why=app.why,
            overall_score=app.score,
            overall_why="Pas de base de données : la disponibilité globale est celle de l'application.",
        )
    db = arch.availability_db
    overall = min(app.score, db.score)
    if app.score == db.score:
        weakest = "l'application et la base de données"
    elif app.score < db.score:
        weakest = "l'application"
    else:
        weakest = "la base de données"
    return AvailabilityDetail(
        application_score=app.score,
        application_why=app.why,
        database_score=db.score,
        database_why=db.why,
        overall_score=overall,
        overall_why=(
            f"La disponibilité globale est limitée par le maillon le plus faible : {weakest} ({overall}/5)."
        ),
    )


def _unmet_requirements(spec: ProjectSpec, arch: ArchitectureDef, availability: AvailabilityDetail) -> list[str]:
    unmet: list[str] = []
    if (
        spec.availability.availability_target == AvailabilityTarget.always_on
        and availability.overall_score <= 2
    ):
        unmet.append("Disponibilité permanente demandée : cette architecture n'offre pas de redondance.")
    if (
        spec.backups.acceptable_data_loss in (LossTolerance.none, LossTolerance.minutes)
        and arch.rpo_class == "daily"
    ):
        unmet.append("Perte de données acceptable très faible : des sauvegardes quotidiennes ne suffisent pas.")
    if spec.team.ops_skill == OpsSkill.none and arch.requires_ops:
        unmet.append("Administration de serveur nécessaire, mais niveau débutant déclaré.")
    return unmet


def _global_warnings(spec: ProjectSpec, tier: str, extra: list[str | None]) -> list[str]:
    warnings = [w for w in extra if w]
    if tier == "l":
        warnings.append(
            "Au-delà de 10 000 utilisateurs par jour, le dimensionnement demande une étude dédiée : "
            "estimation indicative."
        )
    if spec.backups.acceptable_data_loss == LossTolerance.none:
        warnings.append("Une perte de données nulle exige une réplication synchrone, non chiffrée ici.")
    if spec.compliance.payment_data is True:
        warnings.append(
            "Paiements : déléguer à un prestataire de paiement externe est plus simple que de porter "
            "les exigences de sécurité sur l'infrastructure. Ceci n'est pas un avis juridique."
        )
    if len(spec.delivery.environments) > 1:
        warnings.append(
            f"{len(spec.delivery.environments)} environnements demandés : "
            "les coûts ci-dessous ne comptent que la production."
        )
    return warnings


def evaluate(
    spec: ProjectSpec,
    catalog: Catalog | None = None,
    fx: FxTable | None = None,
    with_sensitivity: bool = True,
) -> EvaluationResult:
    from services.questions.coverage import compute_coverage  # import local : évite un couplage au chargement

    catalog = catalog or get_catalog()
    fx = fx or get_fx()

    sizing = build_sizing(spec)
    high_sizing = build_sizing(spec, tier=next_tier(sizing.tier))
    weights, weight_reasons = compute_weights(spec)
    budget_usd, budget_warning = _budget_in_usd(spec, fx)
    rate_usd, rate_warning = _hourly_rate_usd(spec, fx)
    imposed, imposed_warning = _imposed_provider(spec)

    currency = spec.constraints.budget_currency
    display_currency = currency.value if currency else None
    display_rate = fx.rate(display_currency)

    def to_display(amount: float | None) -> float | None:
        if amount is None or not display_rate:
            return None
        return round(amount * display_rate, 2)

    drafts = []
    for arch in get_architectures():
        builder = BUILDERS[arch.id]
        low = builder(catalog, sizing)
        high = builder(catalog, high_sizing)
        eliminated: list[str] = []
        if budget_usd is not None and low.total > budget_usd:
            eliminated.append(
                f"Coût minimal estimé ({low.total:.2f} $ US par mois) supérieur au budget "
                f"({budget_usd:.2f} $ US)."
            )
        if imposed is not None and arch.provider != imposed:
            eliminated.append(f"Fournisseur imposé : {imposed}.")
        drafts.append((arch, low, high, eliminated))

    candidates = [d for d in drafts if not d[3]] or drafts
    cheapest = min(d[1].total for d in candidates)

    results: list[ArchitectureResult] = []
    for arch, low, high, eliminated in drafts:
        availability = _availability(spec, arch)

        cost_why = f"Coût minimal estimé : {low.total:.2f} $ US par mois."
        if not low.complete:
            cost_why += " Estimation incomplète : certains prix sont manquants."
        by_criterion = {
            "cost": CriterionScore(
                criterion="cost",
                score=cost_score(low.total, cheapest),
                weight=weights["cost"],
                why=cost_why,
            ),
            "availability": CriterionScore(
                criterion="availability",
                score=float(availability.overall_score * 20),
                weight=weights["availability"],
                why=availability.overall_why,
            ),
        }
        for criterion in RATED_CRITERIA:
            rating = arch.ratings[criterion]
            by_criterion[criterion] = CriterionScore(
                criterion=criterion,
                score=float(rating.score * 20),
                weight=weights[criterion],
                why=rating.why,
            )
        scores = [by_criterion[name] for name in SCORE_ORDER]
        total = round(sum(s.score * s.weight / 100 for s in scores), 1)

        high_total = max(high.total, low.total)
        within_low, within_high, risk = _budget_status(budget_usd, low.total, high_total)
        warnings = list(dict.fromkeys(low.warnings))
        if risk == BudgetRisk.possible:
            warnings.append(
                f"Au palier supérieur de trafic, le coût estimé ({high_total:.2f} $ US) dépasse le budget "
                f"({budget_usd:.2f} $ US) : le budget n'est pas garanti si le trafic augmente."
            )

        maintenance = (
            round(arch.maintenance_hours_per_month * rate_usd, 2) if rate_usd is not None else None
        )
        total_low_m = round(low.total + maintenance, 2) if maintenance is not None else None
        total_high_m = round(high_total + maintenance, 2) if maintenance is not None else None

        results.append(
            ArchitectureResult(
                id=arch.id,
                provider=arch.provider,
                label=arch.label,
                summary=arch.summary,
                verdict=Verdict.eliminated if eliminated else Verdict.eligible,
                eliminated_reasons=eliminated,
                cost_low=low.total,
                cost_high=high_total,
                cost_low_display=to_display(low.total),
                cost_high_display=to_display(high_total),
                within_budget_low=within_low,
                within_budget_high=within_high,
                budget_risk=risk,
                maintenance_cost_monthly=maintenance,
                maintenance_cost_display=to_display(maintenance),
                total_low_with_maintenance=total_low_m,
                total_high_with_maintenance=total_high_m,
                total_low_with_maintenance_display=to_display(total_low_m),
                total_high_with_maintenance_display=to_display(total_high_m),
                estimate_complete=low.complete and high.complete,
                needs_verification=low.needs_verification or high.needs_verification,
                lines=low.lines,
                graph=build_graph(arch.id, low.lines),
                unpriced=low.unpriced,
                scores=scores,
                total_score=total,
                availability=availability,
                requirements_unmet=_unmet_requirements(spec, arch, availability),
                warnings=warnings,
                maintenance_hours_per_month=arch.maintenance_hours_per_month,
                price_basis=catalog.price_basis(arch.provider),
            )
        )

    results.sort(key=lambda r: (r.verdict == Verdict.eliminated, -r.total_score, r.cost_low))
    recommended_id = None
    for result in results:
        if result.verdict != Verdict.eliminated:
            result.verdict = Verdict.recommended
            recommended_id = result.id
            break

    global_warnings = _global_warnings(spec, sizing.tier, [budget_warning, rate_warning, imposed_warning])

    if recommended_id is not None:
        recommended = next(r for r in results if r.id == recommended_id)
        if recommended.budget_risk == BudgetRisk.possible:
            global_warnings.append(
                f"L'architecture recommandée ({recommended.label}) respecte le budget au palier courant "
                f"({recommended.cost_low:.2f} $ US) mais pas au palier supérieur "
                f"({recommended.cost_high:.2f} $ US) : le budget n'est pas garanti si le trafic augmente."
            )

    if rate_usd is not None:
        live = [r for r in results if r.verdict != Verdict.eliminated]
        if live:
            cheapest_host = min(live, key=lambda r: r.cost_low)
            cheapest_total = min(live, key=lambda r: r.total_low_with_maintenance)
            if cheapest_host.id != cheapest_total.id:
                global_warnings.append(
                    f"{cheapest_host.label} est le moins cher à héberger ({cheapest_host.cost_low:.2f} $ US "
                    f"par mois) mais n'est pas le moins cher avec la maintenance : {cheapest_total.label} "
                    f"coûte {cheapest_total.total_low_with_maintenance:.2f} $ US par mois, maintenance comprise."
                )

    report = compute_coverage(spec)
    if report.missing:
        global_warnings.append(
            f"{len(report.missing)} informations obligatoires manquent : le dimensionnement repose sur "
            "des hypothèses et la recommandation peut changer."
        )
    if report.unknown:
        global_warnings.append(
            f"{len(report.unknown)} réponse(s) « je ne sais pas » remplacée(s) par des hypothèses."
        )

    result = EvaluationResult(
        display_currency=display_currency,
        fx_rate=display_rate,
        fx_as_of=fx.as_of if display_rate and display_currency != "USD" else None,
        pricing_disclaimer=PRICING_DISCLAIMER,
        tier=sizing.tier,
        tier_label=TIER_LABELS[sizing.tier],
        assumptions=list(sizing.assumptions),
        weights=[WeightInfo(criterion=name, weight=value) for name, value in weights.items()],
        weight_reasons=weight_reasons,
        global_warnings=global_warnings,
        ranking=results,
        recommended_id=recommended_id,
        coverage_missing=[f.path for f in report.missing],
    )

    if with_sensitivity:
        result.sensitivity = compute_sensitivity(
            spec,
            result,
            lambda variant: evaluate(variant, catalog=catalog, fx=fx, with_sensitivity=False),
        )
    return result