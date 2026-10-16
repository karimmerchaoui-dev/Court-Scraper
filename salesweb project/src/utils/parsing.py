"""
Shared text-parsing utilities for foreclosure data extraction.
"""

import re


def extract_amount(text: str) -> list[tuple[str, str]]:
    """
    Extract labeled dollar amounts from raw foreclosure page text.

    Recognized labels:
        Upset Price, Upset Amount, Appraised Value,
        Approx. Judgment, Approx. Upset, Debt Amount

    Returns
    -------
    List of (label, dollar_amount) tuples, e.g.:
        [("Approx. Judgment", "$55,758.18"), ...]
    """
    pattern = (
        r"(?im)\b"
        r"(Upset Price|Upset Amount|Appraised Value|"
        r"Approx\. Judgment\*?|Approx\. Upset\*?|Debt Amount)"
        r"\b[^$:\n]*[:\s-]*?"
        r"(\$[\d,]+(?:\.\d{1,2})?)"
    )
    matches = re.findall(pattern, text)
    return [(label.replace("*", "").strip(), amount.strip()) for label, amount in matches]
