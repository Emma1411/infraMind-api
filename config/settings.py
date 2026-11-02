from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "InfraMind API"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"

    max_input_chars: int = 8000
    cors_origins: str = "http://localhost:5173"

    # Protection des routes par clé d'API. Plusieurs clés, séparées par des virgules, permettent
    # de changer de clé sans coupure.
    auth_enabled: bool = True
    api_keys: str = ""

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def api_keys_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()