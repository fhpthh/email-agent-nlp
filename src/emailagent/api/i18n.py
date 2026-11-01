"""Request-local language negotiation; catalogs are loaded once."""
import json
from pathlib import Path

DEFAULT_LOCALE = "vi"
CATALOGS = {
    locale: json.loads((Path(__file__).resolve().parents[1] / "resources" / "locales" / f"{locale}.json").read_text())
    for locale in ("vi", "en")
}


def resolve_locale(header: str) -> str:
    candidates = []
    for index, entry in enumerate(header.split(",")):
        parts = entry.strip().lower().split(";")
        language = parts[0].split("-")[0]
        quality = 1.0
        try:
            for parameter in parts[1:]:
                key, _, value = parameter.strip().partition("=")
                if key == "q":
                    quality = float(value)
        except ValueError:
            continue
        if 0 < quality <= 1 and (language in CATALOGS or language == "*"):
            candidates.append((quality, -index, DEFAULT_LOCALE if language == "*" else language))
    return max(candidates)[2] if candidates else DEFAULT_LOCALE


def translate(code: str, locale: str, field: str = "detail") -> str:
    fallback = CATALOGS[DEFAULT_LOCALE].get(code, CATALOGS[DEFAULT_LOCALE]["HTTP_ERROR"])
    return CATALOGS.get(locale, CATALOGS[DEFAULT_LOCALE]).get(code, fallback)[field]
