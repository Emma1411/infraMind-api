import re
import unicodedata

from models.evaluation import ArchitectureResult
from models.project_spec import ProjectSpec
from services.engine.catalog import Catalog

ALLOWED_PARAMS = frozenset(
    {
        "server_type",
        "vcpu",
        "ram_gb",
        "disk_gb",
        "location",
        "app_slug",
        "monthly_total",
        "backup_cost",
        "ipv4_cost",
        "included_traffic",
        "extra_traffic",
    }
)

DEFAULT_SLUG = "mon-application"


def slugify(name: str | None) -> str:
    if not name:
        return DEFAULT_SLUG
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or DEFAULT_SLUG


def build_params(result: ArchitectureResult, spec: ProjectSpec, catalog: Catalog) -> dict[str, str]:
    plan_line = next(
        (line for line in result.lines if line.item_id.startswith(("hetzner.cpx", "hetzner.ccx"))),
        None,
    )
    if plan_line is None:
        raise ValueError("Aucun serveur Hetzner dans l'estimation.")
    plan = catalog.item(plan_line.item_id)
    backup = next((line for line in result.lines if line.item_id == "hetzner.backup"), None)

    if plan.included_traffic_tb is not None:
        included = f"{plan.included_traffic_tb:g} To"
    else:
        included = "un quota (à vérifier dans la console)"

    return {
        "server_type": plan.id.split(".", 1)[1].upper(),
        "vcpu": str(plan.vcpu),
        "ram_gb": f"{plan.ram_gb:g}",
        "disk_gb": str(plan.disk_gb),
        "location": "Ashburn (ash)",
        "app_slug": slugify(spec.name),
        "monthly_total": f"{result.cost_low:.2f}",
        "backup_cost": f"{backup.monthly:.2f}" if backup else "0.00",
        "ipv4_cost": f"{catalog.amount('hetzner.ipv4_primary'):.2f}",
        "included_traffic": included,
        "extra_traffic": f"{catalog.amount('hetzner.extra_traffic'):.2f}",
    }


PLACEHOLDER_PATTERN = re.compile(r"\[\[([a-zA-Z0-9_]+)\]\]")


def render_placeholders(value, params: dict[str, str]):
    """Remplace récursivement les placeholders du guide."""

    if isinstance(value, str):

        def replace(match):
            key = match.group(1)

            if key not in ALLOWED_PARAMS:
                raise ValueError(
                    f"Placeholder non autorisé : {key}"
                )

            if key not in params:
                raise ValueError(
                    f"Paramètre manquant : {key}"
                )

            return str(params[key])

        return PLACEHOLDER_PATTERN.sub(replace, value)

    if isinstance(value, list):
        return [
            render_placeholders(item, params)
            for item in value
        ]

    if isinstance(value, dict):
        return {
            key: render_placeholders(item, params)
            for key, item in value.items()
        }

    return value


def validate_rendered_guide(guide):
    serialized = guide.model_dump_json()

    remaining = PLACEHOLDER_PATTERN.findall(serialized)

    if remaining:
        raise ValueError(
            f"Placeholders non remplacés : {sorted(set(remaining))}"
        )

    return guide

