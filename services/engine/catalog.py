from functools import lru_cache
from pathlib import Path

from models.catalog import PRICED_STATUSES, PriceItem, ProviderCatalog, Unit

CATALOG_DIR = Path(__file__).resolve().parents[2] / "data" / "catalog"
HOURS_PER_MONTH = 730
PRICING_DISCLAIMER = (
    "Prix de référence pour l'Amérique du Nord uniquement. Le prix réel dépend de la "
    "région technique choisie et peut changer d'une région à l'autre."
)

_HOURLY_UNITS = {Unit.per_hour, Unit.per_vcpu_hour, Unit.per_gb_hour, Unit.per_lcu_hour}
_MONTHLY_UNITS = {Unit.per_month, Unit.per_gb_month, Unit.per_vcpu_month}


class UnknownItem(KeyError):
    """Identifiant absent du catalogue."""


class PriceNotAvailable(Exception):
    """Le prix est indisponible ou manquant : il ne doit jamais être traité comme zéro."""

    def __init__(self, item: PriceItem):
        self.item = item
        super().__init__(f"{item.id} : prix inutilisable (statut {item.status.value})")


class Catalog:
    def __init__(self, providers: list[ProviderCatalog]):
        self.providers: dict[str, ProviderCatalog] = {}
        self._items: dict[str, PriceItem] = {}
        for provider in providers:
            if provider.provider in self.providers:
                raise ValueError(f"Fournisseur en double : {provider.provider}")
            self.providers[provider.provider] = provider
            for item in provider.items:
                if item.id in self._items:
                    raise ValueError(f"Identifiant en double : {item.id}")
                self._items[item.id] = item

    def item(self, item_id: str) -> PriceItem:
        try:
            return self._items[item_id]
        except KeyError:
            raise UnknownItem(item_id) from None

    def is_priced(self, item_id: str) -> bool:
        return self.item(item_id).status in PRICED_STATUSES

    def price_basis(self, provider: str) -> str:
        p = self.providers[provider]
        regions = ", ".join(p.reference_regions)
        return (
            f"{p.label} : prix de référence pour {regions} (Amérique du Nord uniquement), "
            f"relevés du {p.as_of}. {p.region_note}"
        )

    def amount(self, item_id: str) -> float:
        item = self.item(item_id)
        if item.status not in PRICED_STATUSES or item.amount is None:
            raise PriceNotAvailable(item)
        return item.amount

    def monthly_cost(self, item_id: str, quantity: float = 1.0) -> float:
        """Coût mensuel pour une quantité donnée : unités, Go ou vCPU selon l'unité du tarif."""
        item = self.item(item_id)
        amount = self.amount(item_id)
        if item.unit in _MONTHLY_UNITS:
            return amount * quantity
        if item.unit in _HOURLY_UNITS:
            return amount * HOURS_PER_MONTH * quantity
        raise ValueError(
            f"{item_id} : l'unité {item.unit.value} ne se convertit pas en coût mensuel directement"
        )


@lru_cache
def get_catalog() -> Catalog:
    providers = [
        ProviderCatalog.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(CATALOG_DIR.glob("*.json"))
    ]
    return Catalog(providers)