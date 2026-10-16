"""
Unit tests for src.utils.parsing
"""

from src.utils.parsing import extract_amount


class TestExtractAmount:
    def test_upset_price(self):
        text = "Upset Price: $123,456.78"
        result = extract_amount(text)
        assert ("Upset Price", "$123,456.78") in result

    def test_approx_judgment(self):
        text = "Approx. Judgment: $55,758.18"
        result = extract_amount(text)
        assert ("Approx. Judgment", "$55,758.18") in result

    def test_multiple_amounts(self):
        text = (
            "Appraised Value: $200,000.00\n"
            "Upset Price: $150,000.00\n"
            "Debt Amount: $90,000.00"
        )
        result = extract_amount(text)
        labels = [label for label, _ in result]
        assert "Appraised Value" in labels
        assert "Upset Price" in labels
        assert "Debt Amount" in labels

    def test_no_match(self):
        text = "No financial data here."
        result = extract_amount(text)
        assert result == []

    def test_asterisk_stripped(self):
        text = "Approx. Judgment*: $10,000.00"
        result = extract_amount(text)
        labels = [label for label, _ in result]
        assert "Approx. Judgment" in labels
