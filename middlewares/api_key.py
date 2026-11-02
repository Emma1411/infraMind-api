import hmac

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from config.settings import get_settings

API_KEY_HEADER = "X-API-Key"

# auto_error=False : c'est notre fonction qui choisit le message, et le bouton « Authorize » apparaît dans /docs
_api_key_header = APIKeyHeader(name=API_KEY_HEADER, auto_error=False)


def _matches(candidate: str, keys: list[str]) -> bool:
    """Comparaison en temps constant, sur toutes les clés (pas de sortie anticipée)."""
    candidate_bytes = candidate.encode("utf-8")
    matched = False
    for key in keys:
        if hmac.compare_digest(candidate_bytes, key.encode("utf-8")):
            matched = True
    return matched


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return

    keys = settings.api_keys_list
    if not keys:
        # Pas de clé configurée : on refuse tout plutôt que de laisser l'API ouverte
        raise HTTPException(
            status_code=503,
            detail="L'authentification est activée mais aucune clé d'API n'est configurée.",
        )
    if not api_key or not _matches(api_key, keys):
        raise HTTPException(status_code=401, detail="Clé d'API manquante ou invalide.")