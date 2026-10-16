"""
Text parsing utilities for foreclosure listing data.
"""

import re


def extract_amount(text: str) -> list[tuple[str, str]]:
    """
    Extract labeled dollar amounts from foreclosure listing text.

    Returns:
        List of (label, amount) tuples, e.g. [("Approx. Judgment", "$55,758.18"), ...]
    """
    pattern = (
        r"(?im)\b(Upset Price|Upset Amount|Appraised Value"
        r"|Approx\. Judgment\*?|Approx\. Upset\*?)\b"
        r"[^$:\n]*[:\s-]*?(\$[\d,]+(?:\.\d{1,2})?)"
    )
    matches = re.findall(pattern, text)
    return [(label.replace("*", "").strip(), amount.strip()) for label, amount in matches]
