import re
import unicodedata


def normalize_tag(name: str) -> str:
    """Canonical spelling of a tag name as stored in `tags.name`: Unicode
    compatibility forms, case and whitespace folded."""
    s = unicodedata.normalize("NFKC", name).casefold()
    return re.sub(r"\s+", " ", s).strip()
