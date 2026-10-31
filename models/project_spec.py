from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


# ---------- Valeurs possibles ----------

class AppType(str, Enum):
    static_site = "static_site"
    web_app = "web_app"
    api_only = "api_only"
    ssr_app = "ssr_app"
    data_pipeline = "data_pipeline"
    other = "other"


class UsersBand(str, Enum):
    under_100 = "under_100"
    between_100_1000 = "between_100_1000"
    between_1000_10000 = "between_1000_10000"
    over_10000 = "over_10000"


class DatabaseType(str, Enum):
    none = "none"
    relational = "relational"
    document = "document"
    key_value = "key_value"
    other = "other"


class DataSizeBand(str, Enum):
    under_1gb = "under_1gb"
    gb_1_10 = "gb_1_10"
    gb_10_100 = "gb_10_100"
    over_100gb = "over_100gb"


class LossTolerance(str, Enum):
    none = "none"
    minutes = "minutes"
    hours = "hours"
    one_day = "one_day"


class RestoreTime(str, Enum):
    under_1h = "under_1h"
    few_hours = "few_hours"
    one_day = "one_day"
    several_days = "several_days"


class AvailabilityTarget(str, Enum):
    best_effort = "best_effort"
    business_hours = "business_hours"
    always_on = "always_on"


class MonitoringLevel(str, Enum):
    none = "none"
    basic = "basic"
    full = "full"


class Maintainer(str, Enum):
    developer = "developer"
    client = "client"
    client_it = "client_it"
    nobody = "nobody"


class OpsSkill(str, Enum):
    none = "none"
    basic = "basic"
    advanced = "advanced"


class Environment(str, Enum):
    dev = "dev"
    staging = "staging"
    prod = "prod"


class Currency(str, Enum):
    CAD = "CAD"
    USD = "USD"
    EUR = "EUR"


# ---------- Les 12 domaines ----------
# None = non précisé par l'utilisateur.

class _Section(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ApplicationSpec(_Section):
    app_type: AppType | None = None
    runtime: str | None = None
    has_background_jobs: bool | None = None
    needs_realtime: bool | None = None
    third_party_services: list[str] = Field(default_factory=list)


class TrafficSpec(_Section):
    daily_users: UsersBand | None = None
    has_peaks: bool | None = None
    peak_notes: str | None = None


class DataSpec(_Section):
    database_type: DatabaseType | None = None
    data_size: DataSizeBand | None = None
    has_file_uploads: bool | None = None


class BackupsSpec(_Section):
    acceptable_data_loss: LossTolerance | None = None
    acceptable_restore_time: RestoreTime | None = None


class ComplianceSpec(_Section):
    personal_data: bool | None = None
    payment_data: bool | None = None
    health_data: bool | None = None
    other_regulations: str | None = None


class AvailabilitySpec(_Section):
    availability_target: AvailabilityTarget | None = None


class SecuritySpec(_Section):
    auth_required: bool | None = None
    admin_access: bool | None = None
    needs_ddos_protection: bool | None = None
    audit_required: bool | None = None


class NetworkSpec(_Section):
    custom_domain: bool | None = None
    needs_cdn: bool | None = None
    sends_emails: bool | None = None


class DeliverySpec(_Section):
    environments: list[Environment] = Field(default_factory=list)
    ci_cd_wanted: bool | None = None


class ObservabilitySpec(_Section):
    monitoring_level: MonitoringLevel | None = None


class TeamSpec(_Section):
    who_maintains: Maintainer | None = None
    contract_duration_months: int | None = Field(default=None, ge=0)
    ops_skill: OpsSkill | None = None
    hourly_rate: float | None = Field(default=None, ge=0)


class ConstraintsSpec(_Section):
    budget_max_monthly: float | None = Field(default=None, ge=0)
    budget_currency: Currency | None = None
    imposed_provider: str | None = None
    existing_stack_notes: str | None = None
    migration_from: str | None = None


# Ordre d'affichage et de questionnement des domaines
DOMAINS: tuple[str, ...] = (
    "application",
    "traffic",
    "data",
    "backups",
    "compliance",
    "availability",
    "security",
    "network",
    "delivery",
    "observability",
    "team",
    "constraints",
)


class ProjectSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str | None = None

    application: ApplicationSpec = Field(default_factory=ApplicationSpec)
    traffic: TrafficSpec = Field(default_factory=TrafficSpec)
    data: DataSpec = Field(default_factory=DataSpec)
    backups: BackupsSpec = Field(default_factory=BackupsSpec)
    compliance: ComplianceSpec = Field(default_factory=ComplianceSpec)
    availability: AvailabilitySpec = Field(default_factory=AvailabilitySpec)
    security: SecuritySpec = Field(default_factory=SecuritySpec)
    network: NetworkSpec = Field(default_factory=NetworkSpec)
    delivery: DeliverySpec = Field(default_factory=DeliverySpec)
    observability: ObservabilitySpec = Field(default_factory=ObservabilitySpec)
    team: TeamSpec = Field(default_factory=TeamSpec)
    constraints: ConstraintsSpec = Field(default_factory=ConstraintsSpec)

    # Chemins "domaine.champ" auxquels l'utilisateur a répondu « je ne sais pas »
    unknown: list[str] = Field(default_factory=list)