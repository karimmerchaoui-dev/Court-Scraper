"""
Tests for state_normaliser.py — pure logic, no network calls.
"""
import os
import sys

import pytest

# Add the parent directory to sys.path to allow importing state_normaliser
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from state_normaliser import normalise_state

# ── Happy-path cases ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    # Two-letter abbreviations (upper & lower)
    ("NJ",           "New Jersey"),
    ("nj",           "New Jersey"),
    ("FL",           "Florida"),
    ("fl",           "Florida"),
    ("CA",           "California"),
    ("NY",           "New York"),
    ("TX",           "Texas"),
    ("DC",           "District of Columbia"),
    # Full names
    ("New Jersey",   "New Jersey"),
    ("new jersey",   "New Jersey"),
    ("Florida",      "Florida"),
    ("florida",      "Florida"),
    ("New York",     "New York"),
    # Common aliases
    ("Jersey",       "New Jersey"),
    ("jersey",       "New Jersey"),
    # Leading/trailing whitespace should be stripped
    ("  NJ  ",       "New Jersey"),
    ("  Florida  ",  "Florida"),
])
def test_normalise_state_happy_path(raw: str, expected: str) -> None:
    assert normalise_state(raw) == expected


# ── Error cases ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad_input", [
    "XX",          # not a state
    "NewJersey",   # missing space
    "Floridaa",    # typo
    "",            # empty (stripped key = "")
    "  ",          # whitespace only
])
def test_normalise_state_unknown_raises(bad_input: str) -> None:
    with pytest.raises(ValueError, match="Unknown state"):
        normalise_state(bad_input)
