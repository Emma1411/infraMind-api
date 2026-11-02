import json
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from config.settings import get_settings
from models.report import RawReport
from services.llm.client import get_llm_client
from services.llm.prompts.report import REPORT_SYSTEM_PROMPT

MAX_ATTEMPTS = 2  # un appel + une seule correction


class ReportWriterError(Exception):
    """L'IA n'a pas produit un rapport valide."""


def _summarize(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err["loc"]) or "racine"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


async def write_report(
    payload: dict,
    validate: Callable[[RawReport], list[str]],
    client: Any = None,
) -> RawReport:
    settings = get_settings()
    client = client or get_llm_client()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]
    last = "réponse vide"

    for _ in range(MAX_ATTEMPTS):
        response = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1200,
        )
        content = response.choices[0].message.content or ""
        try:
            raw = RawReport.model_validate_json(content)
        except ValidationError as exc:
            problems = [f"json invalide : {_summarize(exc)}"]
        else:
            problems = validate(raw)
            if not problems:
                return raw

        last = " | ".join(problems[:5])
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": (
                    "Ta réponse est refusée pour ces raisons : "
                    + last
                    + ". Corrige-la : n'utilise que les chiffres des données, aucune commande, aucun lien, "
                    "aucun balisage, et respecte le nombre d'éléments demandé. Réponds uniquement avec le json."
                ),
            }
        )

    raise ReportWriterError(last)