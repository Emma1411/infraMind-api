from collections.abc import Callable

from models.evaluation import EvaluationResult, SensitivityEntry, SensitivityScenario
from models.project_spec import ProjectSpec
from services.questions.bank import QUESTION_BANK

# Champs qui font varier le coût, avec leurs valeurs possibles
SENSITIVE_FIELDS: tuple[tuple[str, tuple[object, ...]], ...] = (
    ("traffic.daily_users", ("under_100", "between_100_1000", "between_1000_10000", "over_10000")),
    ("traffic.has_peaks", (False, True)),
    ("data.data_size", ("under_1gb", "gb_1_10", "gb_10_100", "over_100gb")),
    ("data.has_file_uploads", (False, True)),
    ("application.has_background_jobs", (False, True)),
)

# Valeur que le moteur utilise quand l'information manque (voir assumptions.py)
ASSUMED_DEFAULTS: dict[str, object] = {
    "traffic.daily_users": "between_100_1000",
    "traffic.has_peaks": False,
    "data.data_size": "gb_1_10",
    "data.has_file_uploads": False,
    "application.has_background_jobs": False,
}


def _raw(value: object) -> object:
    return value.value if hasattr(value, "value") else value


def _key(value: object) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


def _label(path: str, value: object) -> str:
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    for option in QUESTION_BANK[path].options:
        if option.value == value:
            return option.label
    return str(value)


def _with_value(spec: ProjectSpec, path: str, value: object) -> ProjectSpec:
    data = spec.model_dump(mode="json")
    domain, field = path.split(".", 1)
    data[domain][field] = value
    return ProjectSpec.model_validate(data)


def compute_sensitivity(
    spec: ProjectSpec,
    base: EvaluationResult,
    evaluate_fn: Callable[[ProjectSpec], EvaluationResult],
) -> list[SensitivityEntry]:
    """Pour chaque information qui pèse sur le coût : l'écart de coût de l'architecture recommandée."""
    arch_id = base.recommended_id or base.ranking[0].id
    entries: list[SensitivityEntry] = []

    for path, values in SENSITIVE_FIELDS:
        domain, field = path.split(".", 1)
        current = _raw(getattr(getattr(spec, domain), field))
        status = "known" if current is not None and path not in spec.unknown else "assumed"
        effective = current if current is not None else ASSUMED_DEFAULTS[path]

        scenarios: list[SensitivityScenario] = []
        for value in values:
            result = evaluate_fn(_with_value(spec, path, value))
            arch = next(a for a in result.ranking if a.id == arch_id)
            scenarios.append(
                SensitivityScenario(
                    value=_key(value),
                    label=_label(path, value),
                    cost_low=arch.cost_low,
                    cost_high=arch.cost_high,
                    recommended_id=result.recommended_id,
                    is_current=value == effective,
                )
            )

        costs = [s.cost_low for s in scenarios]
        entries.append(
            SensitivityEntry(
                path=path,
                question=QUESTION_BANK[path].text,
                status=status,
                current_label=_label(path, effective),
                arch_id=arch_id,
                cost_min=min(costs),
                cost_max=max(costs),
                spread=round(max(costs) - min(costs), 2),
                changes_recommendation=any(s.recommended_id != base.recommended_id for s in scenarios),
                scenarios=scenarios,
            )
        )

    entries.sort(key=lambda e: -e.spread)
    return entries