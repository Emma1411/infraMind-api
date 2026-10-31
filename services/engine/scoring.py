from models.project_spec import (
    AvailabilityTarget,
    LossTolerance,
    Maintainer,
    OpsSkill,
    ProjectSpec,
    UsersBand,
)

BASE_WEIGHTS: dict[str, float] = {
    "cost": 20.0,
    "security": 15.0,
    "performance": 10.0,
    "availability": 15.0,
    "scalability": 10.0,
    "maintenance": 15.0,
    "portability": 5.0,
    "rollback": 10.0,
}


def compute_weights(spec: ProjectSpec) -> tuple[dict[str, float], list[str]]:
    """Poids des critères, ajustés selon le projet. Chaque ajustement est expliqué."""
    weights = dict(BASE_WEIGHTS)
    reasons: list[str] = []

    def boost(criterion: str, factor: float, reason: str) -> None:
        weights[criterion] *= factor
        reasons.append(reason)

    if spec.constraints.budget_max_monthly is not None:
        boost("cost", 1.3, "Budget précisé : le coût compte davantage.")

    compliance = spec.compliance
    if compliance.payment_data is True or compliance.health_data is True:
        boost("security", 1.5, "Paiements ou données de santé : la sécurité compte davantage.")
    elif compliance.personal_data is True:
        boost("security", 1.2, "Données personnelles : la sécurité compte un peu plus.")

    target = spec.availability.availability_target
    if target == AvailabilityTarget.always_on:
        boost("availability", 1.6, "Disponibilité permanente demandée : la disponibilité compte davantage.")
    elif target == AvailabilityTarget.business_hours:
        boost("availability", 1.2, "Fiabilité en heures de bureau : la disponibilité compte un peu plus.")
    elif target == AvailabilityTarget.best_effort:
        boost("availability", 0.7, "Quelques pannes acceptables : la disponibilité compte moins.")

    team = spec.team
    if team.ops_skill == OpsSkill.none or team.who_maintains == Maintainer.nobody:
        boost("maintenance", 1.6, "Peu ou pas de compétences en administration : la maintenance compte davantage.")
    elif team.ops_skill == OpsSkill.basic:
        boost("maintenance", 1.2, "Notions de base en administration : la maintenance compte un peu plus.")
    elif team.ops_skill == OpsSkill.advanced:
        boost("maintenance", 0.8, "À l'aise en administration : la maintenance compte moins.")

    if spec.backups.acceptable_data_loss in (LossTolerance.none, LossTolerance.minutes):
        boost("rollback", 1.4, "Très peu de perte de données acceptable : la restauration compte davantage.")

    if spec.traffic.daily_users == UsersBand.over_10000 or spec.traffic.has_peaks is True:
        boost("scalability", 1.4, "Trafic élevé ou pics : la capacité à monter en charge compte davantage.")
        boost("performance", 1.2, "Trafic élevé ou pics : la performance compte davantage.")

    total = sum(weights.values())
    normalized = {name: round(value * 100 / total, 1) for name, value in weights.items()}
    return normalized, reasons


def cost_score(cost: float, cheapest: float) -> float:
    """100 pour l'architecture la moins chère, proportionnel au-delà."""
    if cost <= 0:
        return 100.0
    return round(min(100.0, 100.0 * cheapest / cost), 1)