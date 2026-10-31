from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, model_validator

FX_PATH = Path(__file__).resolve().parents[2] / "data" / "fx.json"


class FxFile(BaseModel):
    as_of: str | None = None
    per_usd: dict[str, float | None]

    @model_validator(mode="after")
    def _check(self) -> "FxFile":
        for currency, rate in self.per_usd.items():
            if rate is not None and rate <= 0:
                raise ValueError(f"Taux invalide pour {currency}")
            if currency != "USD" and rate is not None and not self.as_of:
                raise ValueError("Un taux de change exige une date (as_of)")
        return self


@dataclass(frozen=True)
class FxTable:
    per_usd: dict[str, float | None]
    as_of: str | None = None

    def rate(self, currency: str | None) -> float | None:
        """Unités de la devise pour 1 USD, ou None si non renseigné."""
        if currency is None:
            return None
        if currency == "USD":
            return 1.0
        return self.per_usd.get(currency)


@lru_cache
def get_fx() -> FxTable:
    data = FxFile.model_validate_json(FX_PATH.read_text(encoding="utf-8"))
    return FxTable(per_usd=data.per_usd, as_of=data.as_of)