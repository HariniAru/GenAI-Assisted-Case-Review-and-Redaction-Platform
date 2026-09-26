import pytest

from app.redaction_validation import matches_span


@pytest.mark.parametrize(
    ("text", "start", "expected"),
    [
        ("😀 Ana", 2, True),
        ("Ana", 4, True),
        ("Ana", 5, False),
        ("", 0, False),
        (" ", 1, False),
        ("X", -1, False),
        ("Ana!", 4, False),
    ],
)
def test_exact_span_counts_unicode_code_points(text, start, expected):
    assert matches_span("X 😀 Ana", text, start) is expected
