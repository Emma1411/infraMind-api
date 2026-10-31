from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PriceStatus(str, Enum):
    reported = "reported"        # tarif fourni
    to_verify = "to_verify"      # tarif fourni, à confirmer
    unavailable = "unavailable"  # le service n'existe pas dans cette référence
    missing = "missing"          # prix non fourni


PRICED_STATUSES = {PriceStatus.reported, PriceStatus.to_verify}


class Category(str, Enum):
    compute = "compute"
    database = "database"
    storage = "storage"
    network = "network"
    backup = "backup"


class Unit(str, Enum):
    per_month = "per_month"
    per_hour = "per_hour"
    per_vcpu_hour = "per_vcpu_hour"
    per_gb_hour = "per_gb_hour"
    per_lcu_hour = "per_lcu_hour"
    per_gb_month = "per_gb_month"
    per_vcpu_month = "per_vcpu_month"
    per_gb = "per_gb"
    per_tb = "per_tb"
    per_vcpu_second = "per_vcpu_second"
    per_gb_second = "per_gb_second"
    percent_of_server = "percent_of_server"
    per_million_requests = "per_million_requests"


class PriceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    label: str
    status: PriceStatus
    unit: Unit | None = None
    amount: float | None = Field(default=None, ge=0)
    vcpu: int | None = None
    ram_gb: float | None = None
    disk_gb: int | None = None
    # Quantité gratuite par mois, dans l'unité de facturation de l'entrée
    free_quota: float | None = Field(default=None, ge=0)
    # Trafic sortant inclus par mois, en To, quand il est connu avec précision
    included_traffic_tb: float | None = Field(default=None, ge=0)
    note: str | None = None

    @model_validator(mode="after")
    def _amount_matches_status(self) -> "PriceItem":
        priced = self.status in PRICED_STATUSES
        if priced and (self.amount is None or self.unit is None):
            raise ValueError(f"{self.id} : un prix doit avoir un montant et une unité")
        if not priced and (self.amount is not None or self.unit is not None):
            raise ValueError(
                f"{self.id} : un service indisponible ou sans prix ne peut pas avoir de montant"
            )
        if not priced and self.free_quota is not None:
            raise ValueError(f"{self.id} : un quota gratuit exige un prix")
        return self


class ProviderCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    label: str
    scope: str = "north_america"
    # Régions techniques sur lesquelles les prix ont été relevés
    reference_regions: list[str] = Field(min_length=1)
    region_note: str = Field(min_length=1)
    currency: str = "USD"
    as_of: str = Field(pattern=r"^\d{4}-\d{2}(-\d{2})?$")
    source: str
    items: list[PriceItem]

    @model_validator(mode="after")
    def _ids_are_prefixed(self) -> "ProviderCatalog":
        for item in self.items:
            if not item.id.startswith(f"{self.provider}."):
                raise ValueError(f"{item.id} : l'identifiant doit commencer par « {self.provider}. »")
        return self