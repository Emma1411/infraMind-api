import re

# (motif, remplacement)
_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "[MASQUÉ]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[MASQUÉ]"),
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "[MASQUÉ]"),
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "[MASQUÉ]"),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "[MASQUÉ]"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "[MASQUÉ]"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[MASQUÉ]"),
    # identifiants dans une URL de connexion : scheme://user:pass@hote
    (re.compile(r"(\b[a-z][a-z0-9+.\-]*://)[^\s/@]+:[^\s/@]+@", re.IGNORECASE), r"\1[MASQUÉ]@"),
    # password: xxx, token=xxx, api_key: xxx
    (
        re.compile(r"\b(password|passwd|pwd|secret|token|api[_-]?key)\b(\s*[:=]\s*)\S+", re.IGNORECASE),
        r"\1\2[MASQUÉ]",
    ),
]


def mask_secrets(text: str) -> str:
    """Masque les motifs évidents de secrets avant tout envoi à l'IA."""
    for pattern, replacement in _RULES:
        text = pattern.sub(replacement, text)
    return text