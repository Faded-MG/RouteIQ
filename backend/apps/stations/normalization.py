"""City normalization utilities for station matching against gazetteer."""

import re


def normalize_city(city: str) -> str:
    """Normalize city name for consistent gazetteer lookup."""
    s = city.lower().strip()
    s = re.sub(r"\(balance\)", "", s)
    pattern = (
        r"\b(county|city|town|township|cdp|village|borough|charter township|"
        r"plantation|metropolitan government|unified government|consolidated government)\b"
    )
    s = re.sub(pattern, "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\bst\b", "saint", s)
    s = re.sub(r"\bste\b", "sainte", s)
    s = re.sub(r"\bft\b", "fort", s)
    s = re.sub(r"\bmt\b", "mount", s)
    s = s.replace(" ", "")
    return s
