"""Unit tests for text parsing utilities."""

from src.utils.parsers import extract_amount


def test_extract_upset_price():
    text = "Upset Price: $123,456.78"
    result = extract_amount(text)
    assert len(result) == 1
    assert result[0][0] == "Upset Price"
    assert result[0][1] == "$123,456.78"


def test_extract_multiple_amounts():
    text = (
        "Approx. Judgment: $55,758.18\n"
        "Approx. Upset: $60,000.00\n"
        "Upset Price: $62,500.00"
    )
    result = extract_amount(text)
    labels = [r[0] for r in result]
    assert "Approx. Judgment" in labels
    assert "Approx. Upset" in labels
    assert "Upset Price" in labels


def test_extract_amount_empty_text():
    assert extract_amount("") == []


def test_extract_amount_no_match():
    assert extract_amount("No financial data here.") == []
