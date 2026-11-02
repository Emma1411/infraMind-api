from models.evaluation import ArchitectureResult, EvaluationResult, Verdict
from models.report import ArchNote, Report
from services.export.quote import money
from services.report.payload import CRITERIA_FR, safe_warnings, strengths_and_weaknesses


def _score(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _range(arch: ArchitectureResult) -> str:
    return f"de {money(arch.cost_low)} à {money(arch.cost_high)} par mois"


def _other_note(arch: ArchitectureResult) -> str:
    if arch.verdict == Verdict.eliminated:
        return "Éliminée : " + " ".join(arch.eliminated_reasons)
    _, worst = strengths_and_weaknesses(arch, n=1)
    weak = worst[0]
    return (
        f"Note de {_score(arch.total_score)} sur 100, coût {_range(arch)}. "
        f"Point faible principal : {CRITERIA_FR[weak.criterion]} ({int(round(weak.score / 20))}/5), {weak.why}"
    )


def template_report(result: EvaluationResult) -> Report:
    """Rapport écrit par du code : rapport de secours, et seul rapport quand rien n'est recommandé."""
    recommended = next((a for a in result.ranking if a.id == result.recommended_id), None)
    others = [a for a in result.ranking if a.id != result.recommended_id]
    notes = [ArchNote(arch_id=a.id, text=_other_note(a)) for a in others]

    if recommended is None:
        return Report(
            summary=(
                "Aucune des architectures étudiées ne respecte toutes les contraintes de ton projet. "
                "Les raisons de chaque élimination sont détaillées ci-dessous."
            ),
            why_this_one=[],
            why_not_others=notes,
            watch_out=safe_warnings(result)[:4] or ["Cette analyse est une estimation : revérifie les prix avant de t'engager."],
            next_steps=["Revois le budget ou les contraintes imposées, puis relance l'analyse."],
        )

    best, _ = strengths_and_weaknesses(recommended, n=3)
    reasons = [
        f"{CRITERIA_FR[s.criterion].capitalize()} ({int(round(s.score / 20))}/5) : {s.why}" for s in best
    ]
    cost = next(s for s in recommended.scores if s.criterion == "cost")
    reasons.append(f"Coût : {cost.why}")

    warnings: list[str] = []
    for text in safe_warnings(result)[:3] + recommended.warnings[:2]:
        if text not in warnings:
            warnings.append(text)
    if not warnings:
        warnings.append("Cette analyse est une estimation : revérifie les prix avant de t'engager.")

    steps: list[str] = []
    if result.coverage_missing:
        steps.append("Complète les informations manquantes pour affiner l'estimation.")
    steps.append("Ouvre le guide de déploiement de cette architecture.")
    steps.append("Télécharge la section infrastructure du devis.")

    return Report(
        summary=(
            f"Pour un projet de {result.tier_label}, l'architecture la mieux adaptée est « {recommended.label} » "
            f"(note de {_score(recommended.total_score)} sur 100). Son coût d'hébergement estimé va "
            f"{_range(recommended)}, hors taxes."
        ),
        why_this_one=reasons[:4],
        why_not_others=notes,
        watch_out=warnings[:4],
        next_steps=steps[:3],
    )