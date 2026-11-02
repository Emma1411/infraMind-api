from collections.abc import Callable
from datetime import date, timedelta

from models.evaluation import ArchitectureResult, EvaluationResult, Verdict
from models.export import QuoteResponse
from models.project_spec import ProjectSpec
from services.engine.evaluate import evaluate
from services.engine.fx import FxTable
from services.guides.hetzner import slugify
from services.questions.bank import QUESTION_BANK

CURRENCY_LABELS = {"USD": "$ US", "CAD": "$ CA", "EUR": "€"}


class UnknownQuoteArchitecture(KeyError):
    """Identifiant d'architecture absent du résultat."""


class NoRecommendation(ValueError):
    """Aucune architecture n'est recommandée : l'utilisateur doit en choisir une."""


def money(amount: float, label: str = "$ US") -> str:
    text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} {label}"


def escape(text: str) -> str:
    """Protège le texte pour un tableau Markdown : barres verticales et retours à la ligne."""
    return " ".join(text.replace("|", "\\|").split())


def _formatter(result: EvaluationResult) -> Callable[[float], str]:
    def fmt(usd: float) -> str:
        base = money(usd)
        currency = result.display_currency
        if result.fx_rate and currency and currency != "USD":
            label = CURRENCY_LABELS.get(currency, currency)
            return f"{base} (≈ {money(usd * result.fx_rate, label)})"
        return base

    return fmt


def _select(result: EvaluationResult, arch_id: str | None) -> ArchitectureResult:
    if arch_id is None:
        if result.recommended_id is None:
            raise NoRecommendation("Aucune architecture n'est recommandée : choisis-en une.")
        arch_id = result.recommended_id
    arch = next((r for r in result.ranking if r.id == arch_id), None)
    if arch is None:
        raise UnknownQuoteArchitecture(arch_id)
    return arch


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def build_quote(
    spec: ProjectSpec,
    arch_id: str | None = None,
    client_name: str | None = None,
    validity_days: int = 30,
    margin_percent: float = 20.0,
    include_alternatives: bool = True,
    today: date | None = None,
    fx: FxTable | None = None,
) -> QuoteResponse:
    today = today or date.today()
    valid_until = today + timedelta(days=validity_days)
    result = evaluate(spec, fx=fx)
    arch = _select(result, arch_id)
    fmt = _formatter(result)
    project = escape(spec.name) if spec.name else "Projet"

    out: list[str] = [
        "# Section « Infrastructure » du devis",
        "",
        f"**Projet :** {project}",
    ]
    if client_name:
        out.append(f"**Client :** {escape(client_name)}")
    out += [
        f"**Date de l'estimation :** {today.isoformat()}",
        f"**Estimation valable jusqu'au :** {valid_until.isoformat()}",
        "",
    ]

    # 1. Recommandation
    out += [
        "## 1. Recommandation",
        "",
        f"**Architecture :** {arch.label}. {arch.summary}",
        "",
        f"**Coût d'hébergement estimé :** de {fmt(arch.cost_low)} à {fmt(arch.cost_high)} par mois, hors taxes.",
        "",
        f"La borne basse correspond au palier de trafic retenu ({result.tier_label}). "
        "La borne haute correspond au palier de trafic suivant.",
        "",
    ]
    if arch.id == result.recommended_id:
        out += [f"C'est l'architecture recommandée par l'analyse (note : {arch.total_score:g} sur 100).", ""]
    else:
        out += [f"Architecture choisie manuellement (note : {arch.total_score:g} sur 100).", ""]
    if arch.verdict == Verdict.eliminated:
        out += [
            "**Attention : cette architecture est éliminée par les contraintes du projet :** "
            + " ".join(arch.eliminated_reasons),
            "",
        ]
    if arch.needs_verification:
        out += ["Certains prix du catalogue sont à vérifier (ils sont signalés dans le détail).", ""]
    if not arch.estimate_complete:
        out += ["Estimation incomplète : des prix manquent (voir la section 9).", ""]

    # 2. Coûts récurrents
    out += ["## 2. Coûts récurrents (par mois)", ""]
    nodes = [n for n in (arch.graph.nodes if arch.graph else []) if n.monthly_cost > 0]
    if nodes:
        out += ["| Composant | Coût mensuel |", "|---|---:|"]
        out += [f"| {escape(n.label)} | {fmt(n.monthly_cost)} |" for n in nodes]
        out.append("")
    out += ["Détail des lignes de coût (palier de trafic retenu) :", ""]
    out += ["| Service | Détail | Coût mensuel |", "|---|---|---:|"]
    for line in arch.lines:
        label = escape(line.label) + (" (prix à vérifier)" if line.to_verify else "")
        out.append(f"| {label} | {escape(line.detail)} | {fmt(line.monthly)} |")
    out += [f"| **Total** | | **{fmt(arch.cost_low)}** |", ""]

    # 3. Maintenance
    out += [
        "## 3. Maintenance",
        "",
        f"Temps de maintenance estimé pour cette architecture : **{arch.maintenance_hours_per_month:g} h par mois** "
        "(mises à jour, surveillance, incidents courants). C'est du travail à facturer, en plus de l'hébergement. "
        "Cette estimation d'heures est une valeur de départ à ajuster.",
        "",
    ]
    if arch.maintenance_cost_monthly is not None:
        out += [
            f"À ton tarif horaire, cela représente {fmt(arch.maintenance_cost_monthly)} par mois, soit un total de "
            f"{fmt(arch.total_low_with_maintenance)} à {fmt(arch.total_high_with_maintenance)} par mois avec l'hébergement.",
            "",
        ]
    else:
        out += ["Tarif horaire non renseigné : renseigne-le pour chiffrer ce poste.", ""]

    # 4. Coûts ponctuels
    out += [
        "## 4. Coûts ponctuels à prévoir",
        "",
        "Ces éléments ne sont pas chiffrés par l'outil. À compléter avant d'envoyer le devis :",
        "",
        "- Nom de domaine (achat annuel chez un registraire) : ______",
        "- Mise en place et déploiement (temps de travail) : ______",
        "- Environnements supplémentaires (test, préproduction) : ______. L'estimation ne couvre que la production.",
        "- Services non compris (courriels transactionnels, surveillance externe) : ______",
        "",
    ]

    # 5. Facturation
    suggested = arch.cost_high * (1 + margin_percent / 100)
    out += [
        "## 5. Comment facturer l'hébergement",
        "",
        "Deux façons de faire, à choisir avec le client :",
        "",
        "**Option A (recommandée) : le client paie directement le fournisseur.** Tu factures seulement la mise en "
        "place et la maintenance. Aucun risque de dépassement pour toi.",
        "",
        f"**Option B : forfait mensuel refacturé.** Tu paies le fournisseur et tu refactures. Montant suggéré : "
        f"{fmt(suggested)} par mois (haut de la fourchette, {fmt(arch.cost_high)}, plus une marge de "
        f"{margin_percent:g} %). Si le trafic réel dépasse le palier supérieur, ce montant peut ne pas suffire : "
        "prévois une clause de révision.",
        "",
    ]

    # 6. Hypothèses
    out += ["## 6. Hypothèses retenues", ""]
    out += [f"- {assumption}" for assumption in result.assumptions]
    out.append("")

    # 7. Points à confirmer
    out += ["## 7. Points à confirmer avec le client", ""]
    missing = [QUESTION_BANK[p].text for p in result.coverage_missing if p in QUESTION_BANK]
    unknown = [QUESTION_BANK[p].text for p in spec.unknown if p in QUESTION_BANK]
    if missing:
        out += ["Informations manquantes (le dimensionnement repose sur des hypothèses) :", ""]
        out += [f"- {question}" for question in missing]
        out.append("")
    if unknown:
        out += ["Réponses « je ne sais pas » à clarifier :", ""]
        out += [f"- {question}" for question in unknown]
        out.append("")
    if not missing and not unknown:
        out += ["Toutes les informations obligatoires ont été renseignées.", ""]

    # 8. Sensibilité
    out += ["## 8. Ce qui peut faire varier le prix", ""]
    entries = [e for e in result.sensitivity[:3] if e.arch_id == arch.id]
    if entries:
        for entry in entries:
            status = "hypothèse à confirmer" if entry.status == "assumed" else "réponse donnée"
            line = (
                f"- **{entry.question}** ({status}, valeur retenue : {entry.current_label}) : "
                f"le coût mensuel varie de {fmt(entry.cost_min)} à {fmt(entry.cost_max)}."
            )
            if entry.changes_recommendation:
                line += " Une autre valeur changerait l'architecture recommandée."
            out.append(line)
        out.append("")
    else:
        out += ["La sensibilité n'est calculée que pour l'architecture recommandée.", ""]

    # 9. Risques et limites
    risks = _unique(
        list(result.global_warnings)
        + list(arch.warnings)
        + list(arch.requirements_unmet)
        + (["Certains prix du catalogue sont à vérifier avant de s'engager."] if arch.needs_verification else [])
        + [f"Prix manquant : {u.label} ({u.reason})." for u in arch.unpriced]
    )
    out += ["## 9. Risques et limites", ""]
    out += [f"- {risk}" for risk in risks] or ["Aucun point particulier."]
    out.append("")

    # 10. Alternatives
    if include_alternatives:
        out += ["## 10. Alternatives étudiées", ""]
        out += ["| Architecture | Coût mensuel | Note sur 100 | Statut |", "|---|---:|---:|---|"]
        for item in result.ranking:
            if item.verdict == Verdict.eliminated:
                status = "Éliminée : " + escape(" ".join(item.eliminated_reasons))
            elif item.id == arch.id:
                status = "Choisie"
            else:
                status = "Éligible"
            cost = f"{fmt(item.cost_low)} à {fmt(item.cost_high)}" + ("" if item.estimate_complete else " (incomplet)")
            out.append(f"| {escape(item.label)} | {cost} | {item.total_score:g} | {status} |")
        out.append("")

    # Base des prix
    out += [
        "## Base des prix et avertissement",
        "",
        arch.price_basis,
        "",
        result.pricing_disclaimer,
        "",
        "Ces montants sont des estimations établies à partir de tarifs publics de référence. Ils ne constituent pas "
        f"un engagement et doivent être revérifiés avant signature. Estimation valable jusqu'au {valid_until.isoformat()}.",
        "",
    ]

    return QuoteResponse(
        arch_id=arch.id,
        filename=f"devis-infrastructure-{slugify(spec.name)}-{today.isoformat()}.md",
        markdown="\n".join(out),
        generated_on=today.isoformat(),
        valid_until=valid_until.isoformat(),
    )