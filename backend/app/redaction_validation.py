"""One exact-span rule for manual redactions and AI proposals."""


def matches_span(description: str, text: str, start: int) -> bool:
    """Offsets count Unicode code points, as Python string slicing does."""
    return bool(
        text.strip()
        and start >= 0
        and start + len(text) <= len(description)
        and description[start : start + len(text)] == text
    )
