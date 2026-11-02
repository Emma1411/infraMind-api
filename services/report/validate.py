import re
from typing import Any

from models.report import RawReport

MAX_SUMMARY = 700
MAX_ITEM = 320
MAX_NOTE = 280
MAX_STEP = 240
FREE_INTEGER_LIMIT = 10  # les petits entiers (nombre de raisons, notes sur 5) sont toujours permis
TOLERANCE = 0.006

NUMBER = re.compile(r"\d+(?:[ \u00a0]\d{3})*(?:[.,]\d+)?")
FORBIDDEN = re.compile(
    r"```|`|https?://|www\.|<[a-z/]|\*\*"
    r"|\b(?:sudo|terraform|docker|gcloud|curl|chmod|apt-get)\b|\brm\s+-|\bapt\s+(?:install|update|upgrade)\b",
    re.IGNORECASE,
)


def parse_numbers(text: str) -> list[float]:
    values: list[float] = []
    for raw in NUMBER.findall(text):
        cleaned = raw.replace("\u00a0", "").replace(" ", "").replace(",", ".")
        try:
            values.append(float(cleaned))
        except ValueError:
            continue
    return values


def allowed_numbers(payload: Any) -> set[float]:
    found: set[float] = set()

    def walk(value: Any) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            number = float(value)
            found.update({number, float(round(number)), round(number, 1), round(number, 2), float(int(number))})
        elif isinstance(value, str):
            found.update(parse_numbers(value))
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(payload)
    return found


def number_problems(texts: list[str], allowed: set[float]) -> list[str]:
    invented: list[str] = []
    for text in texts:
        for number in parse_numbers(text):
            if number.is_integer() and number <= FREE_INTEGER_LIMIT:
                continue
            if any(abs(number - known) < TOLERANCE for known in allowed):
                continue
            label = f"{number:g}"
            if label not in invented:
                invented.append(label)
    return [f"chiffre absent des données : {value}" for value in invented]


def _check_list(name: str, items: list[str], low: int, high: int, max_len: int, problems: list[str]) -> None:
    if not low <= len(items) <= high:
        problems.append(f"{name} doit contenir de {low} à {high} éléments (il en contient {len(items)}).")
    for item in items:
        if not item.strip():
            problems.append(f"{name} contient un élément vide.")
        elif len(item) > max_len:
            problems.append(f"{name} : un élément dépasse {max_len} caractères.")


def validate_raw(raw: RawReport, payload: dict) -> list[str]:
    problems: list[str] = []
    others = set(payload["others_to_explain"])
    notes = {key: text for key, text in raw.why_not_others.items() if key in others}

    if not raw.summary.strip():
        problems.append("summary est vide.")
    elif len(raw.summary) > MAX_SUMMARY:
        problems.append(f"summary dépasse {MAX_SUMMARY} caractères.")
    _check_list("why_this_one", raw.why_this_one, 2, 4, MAX_ITEM, problems)
    _check_list("watch_out", raw.watch_out, 1, 4, MAX_ITEM, problems)
    _check_list("next_steps", raw.next_steps, 1, 3, MAX_STEP, problems)
    for key, text in notes.items():
        if not text.strip() or len(text) > MAX_NOTE:
            problems.append(f"why_not_others[{key}] est vide ou dépasse {MAX_NOTE} caractères.")

    texts = [raw.summary, *raw.why_this_one, *notes.values(), *raw.watch_out, *raw.next_steps]
    for text in texts:
        if FORBIDDEN.search(text):
            problems.append(f"contenu interdit (code, lien, commande ou balisage) : « {text[:60]} »")
            break
    problems.extend(number_problems(texts, allowed_numbers(payload)))
    return problems