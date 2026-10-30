from dataclasses import dataclass
from enum import Enum
from typing import Any

from models.project_spec import DOMAINS, DatabaseType, ProjectSpec


class FieldStatus(str, Enum):
    KNOWN = "known"
    UNKNOWN = "unknown"  # l'utilisateur a répondu « je ne sais pas »
    MISSING = "missing"


# Champs qu'un DevOps veut connaître avant de recommander quoi que ce soit
REQUIRED_FIELDS: dict[str, list[str]] = {
    "application": ["app_type", "has_background_jobs"],
    "traffic": ["daily_users", "has_peaks"],
    "data": ["database_type", "data_size", "has_file_uploads"],
    "backups": ["acceptable_data_loss", "acceptable_restore_time"],
    "compliance": ["personal_data", "payment_data", "health_data"],
    "availability": ["availability_target"],
    "security": ["auth_required", "admin_access"],
    "network": ["custom_domain", "sends_emails"],
    "delivery": ["environments"],
    "observability": ["monitoring_level"],
    "team": ["who_maintains", "ops_skill"],
    "constraints": ["budget_max_monthly", "budget_currency"],
}

# Questions inutiles si l'utilisateur a dit : pas de base de données ET pas de fichiers
_STORAGE_DEPENDENT: set[tuple[str, str]] = {
    ("data", "data_size"),
    ("backups", "acceptable_data_loss"),
    ("backups", "acceptable_restore_time"),
}


@dataclass(frozen=True)
class FieldCoverage:
    domain: str
    field: str
    status: FieldStatus

    @property
    def path(self) -> str:
        return f"{self.domain}.{self.field}"


@dataclass(frozen=True)
class CoverageReport:
    fields: list[FieldCoverage]

    @property
    def missing(self) -> list[FieldCoverage]:
        return [f for f in self.fields if f.status == FieldStatus.MISSING]

    @property
    def unknown(self) -> list[FieldCoverage]:
        return [f for f in self.fields if f.status == FieldStatus.UNKNOWN]

    @property
    def is_complete(self) -> bool:
        return not self.missing

    def domain_status(self) -> dict[str, str]:
        """complete / partial / missing pour chaque domaine."""
        result: dict[str, str] = {}
        for domain in DOMAINS:
            items = [f for f in self.fields if f.domain == domain]
            missing = [f for f in items if f.status == FieldStatus.MISSING]
            if not missing:
                result[domain] = "complete"
            elif len(missing) == len(items):
                result[domain] = "missing"
            else:
                result[domain] = "partial"
        return result


def _storage_in_use(spec: ProjectSpec) -> bool:
    no_database = spec.data.database_type == DatabaseType.none
    no_uploads = spec.data.has_file_uploads is False
    return not (no_database and no_uploads)


def _is_applicable(spec: ProjectSpec, domain: str, field: str) -> bool:
    if (domain, field) in _STORAGE_DEPENDENT:
        return _storage_in_use(spec)
    return True


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return True


def compute_coverage(spec: ProjectSpec) -> CoverageReport:
    items: list[FieldCoverage] = []
    for domain in DOMAINS:
        section = getattr(spec, domain)
        for field in REQUIRED_FIELDS[domain]:
            if not _is_applicable(spec, domain, field):
                continue
            path = f"{domain}.{field}"
            if _is_filled(getattr(section, field)):
                status = FieldStatus.KNOWN
            elif path in spec.unknown:
                status = FieldStatus.UNKNOWN
            else:
                status = FieldStatus.MISSING
            items.append(FieldCoverage(domain, field, status))
    return CoverageReport(items)