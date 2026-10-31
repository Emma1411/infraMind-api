from dataclasses import dataclass

from models.project_spec import DatabaseType, DataSizeBand, ProjectSpec, UsersBand

TIERS: tuple[str, ...] = ("xs", "s", "m", "l")

TIER_LABELS = {
    "xs": "moins de 100 utilisateurs par jour",
    "s": "100 à 1 000 utilisateurs par jour",
    "m": "1 000 à 10 000 utilisateurs par jour",
    "l": "plus de 10 000 utilisateurs par jour",
}

_BAND_TO_TIER = {
    UsersBand.under_100: "xs",
    UsersBand.between_100_1000: "s",
    UsersBand.between_1000_10000: "m",
    UsersBand.over_10000: "l",
}

# Utilisateurs par jour représentatifs de chaque palier (hypothèse d'ingénierie)
TIER_USERS = {"xs": 50, "s": 500, "m": 5000, "l": 20000}

_DB_GB = {
    DataSizeBand.under_1gb: 1.0,
    DataSizeBand.gb_1_10: 10.0,
    DataSizeBand.gb_10_100: 100.0,
    DataSizeBand.over_100gb: 200.0,
}

DAYS_PER_MONTH = 30
MB_EGRESS_PER_USER_PER_DAY = 5.0
REQUESTS_PER_USER_PER_DAY = 30
SECONDS_PER_REQUEST = 0.3
FILES_GB_WHEN_UPLOADS = 20.0
DEFAULT_DB_GB = 10.0


@dataclass(frozen=True)
class Sizing:
    tier: str
    users_per_day: int
    has_database: bool
    db_gb: float
    files_gb: float
    egress_gb: float
    requests_per_month: float
    instance_billing: bool
    assumptions: tuple[str, ...]


def next_tier(tier: str) -> str:
    return TIERS[min(TIERS.index(tier) + 1, len(TIERS) - 1)]


def _base_tier(spec: ProjectSpec) -> tuple[str, list[str]]:
    notes: list[str] = []
    band = spec.traffic.daily_users
    if band is None:
        tier = "s"
        notes.append("Trafic non précisé : le palier « 100 à 1 000 utilisateurs par jour » est supposé.")
    else:
        tier = _BAND_TO_TIER[band]

    if spec.traffic.has_peaks is True:
        bumped = next_tier(tier)
        if bumped != tier:
            notes.append("Pics de trafic : dimensionnement d'un palier au-dessus.")
        tier = bumped

    notes.append(f"Palier de dimensionnement : {TIER_LABELS[tier]}.")
    return tier, notes


def build_sizing(spec: ProjectSpec, tier: str | None = None) -> Sizing:
    notes: list[str] = []
    if tier is None:
        tier, tier_notes = _base_tier(spec)
        notes.extend(tier_notes)

    users = TIER_USERS[tier]

    db_type = spec.data.database_type
    has_database = db_type != DatabaseType.none
    if db_type is None:
        notes.append("Type de base non précisé : une base relationnelle est supposée.")
    if has_database:
        if spec.data.data_size is None:
            db_gb = DEFAULT_DB_GB
            notes.append("Taille des données non précisée : 10 Go supposés.")
        else:
            db_gb = _DB_GB[spec.data.data_size]
    else:
        db_gb = 0.0

    if spec.data.has_file_uploads is True:
        files_gb = FILES_GB_WHEN_UPLOADS
        notes.append(f"Envoi de fichiers : {FILES_GB_WHEN_UPLOADS:.0f} Go de stockage supposés.")
    else:
        files_gb = 0.0
        if spec.data.has_file_uploads is None:
            notes.append("Envoi de fichiers non précisé : aucun fichier supposé.")

    egress_gb = users * DAYS_PER_MONTH * MB_EGRESS_PER_USER_PER_DAY / 1000
    requests = float(users * DAYS_PER_MONTH * REQUESTS_PER_USER_PER_DAY)

    instance_billing = bool(spec.application.has_background_jobs) or bool(spec.application.needs_realtime)

    notes.append(
        f"Trafic sortant supposé : {MB_EGRESS_PER_USER_PER_DAY:g} Mo par utilisateur et par jour "
        f"({egress_gb:.0f} Go par mois)."
    )
    notes.append(
        f"Requêtes supposées : {REQUESTS_PER_USER_PER_DAY} par utilisateur et par jour, "
        f"{SECONDS_PER_REQUEST} s en moyenne par requête."
    )
    notes.append("Coûts calculés sur 730 heures par mois, pour l'environnement de production seulement.")

    return Sizing(
        tier=tier,
        users_per_day=users,
        has_database=has_database,
        db_gb=db_gb,
        files_gb=files_gb,
        egress_gb=egress_gb,
        requests_per_month=requests,
        instance_billing=instance_billing,
        assumptions=tuple(notes),
    )