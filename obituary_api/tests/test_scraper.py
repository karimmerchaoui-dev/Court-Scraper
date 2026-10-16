"""
Tests for scraper.py helper functions.

All external calls (requests, Mistral) are mocked.
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from scraper import (
    _clean_html,
    _extract_obituary_data,
    _run_llm_extraction,
    get_obituary_info,
)

# ── _clean_html ───────────────────────────────────────────────────────────────

def test_clean_html_removes_script_tags() -> None:
    html = "<html><body><p>Hello</p><script>alert(1)</script></body></html>"
    cleaned = _clean_html(html)
    assert "<script>" not in cleaned
    assert "Hello" in cleaned


def test_clean_html_removes_style_tags() -> None:
    html = "<html><body><p>Hi</p><style>.red{color:red}</style></body></html>"
    cleaned = _clean_html(html)
    assert "<style>" not in cleaned
    assert "Hi" in cleaned


def test_clean_html_removes_multiple_useless_tags() -> None:
    html = """
    <html>
      <head><meta charset="utf-8"><link rel="stylesheet" href="a.css"></head>
      <body>
        <img src="photo.jpg">
        <svg><rect/></svg>
        <p>Obituary text here.</p>
        <noscript>Enable JS</noscript>
      </body>
    </html>
    """
    cleaned = _clean_html(html)
    assert "<img" not in cleaned
    assert "<svg" not in cleaned
    assert "<noscript" not in cleaned
    assert "Obituary text here." in cleaned


def test_clean_html_preserves_content_tags() -> None:
    html = "<html><body><h1>Name</h1><p>Born 1940, died 2023.</p></body></html>"
    cleaned = _clean_html(html)
    assert "<h1>" in cleaned
    assert "<p>" in cleaned


# ── _run_llm_extraction ───────────────────────────────────────────────────────

_FAKE_LLM_RESPONSE = {
    "name":           "John Doe",
    "obituary_text":  "John was beloved.",
    "age":            83,
    "friends":        [],
    "associates":     [],
    "heirs":          [{"name": "Jane Doe", "relationship": "spouse"}],
    "date_of_death":  "2023-06-30",
    "place_of_death": "Trenton, NJ",
    "date_of_birth":  "1940-01-15",
    "place_of_birth": "Newark, NJ",
}


@patch("obituary_api.scraper.Mistral")
def test_run_llm_extraction_returns_parsed_dict(MockMistral: MagicMock) -> None:
    # Build the fake response chain
    fake_choice = MagicMock()
    fake_choice.message.content = json.dumps(_FAKE_LLM_RESPONSE)
    MockMistral.return_value.chat.complete.return_value.choices = [fake_choice]

    result = _run_llm_extraction("<p>Some obituary HTML</p>")

    assert result["name"] == "John Doe"
    assert result["age"] == 83
    assert result["heirs"][0]["relationship"] == "spouse"


# ── _extract_obituary_data ────────────────────────────────────────────────────

@patch("obituary_api.scraper._run_llm_extraction", return_value=_FAKE_LLM_RESPONSE)
@patch("obituary_api.scraper._fetch_rendered_html", return_value="<html>...</html>")
def test_extract_obituary_data_non_legacy(
    mock_fetch: MagicMock, mock_llm: MagicMock
) -> None:
    result = _extract_obituary_data("https://example.com/obit/john-doe")
    mock_fetch.assert_called_once()
    mock_llm.assert_called_once()
    assert result["name"] == "John Doe"


@patch("obituary_api.scraper._run_llm_extraction", return_value=_FAKE_LLM_RESPONSE)
@patch(
    "obituary_api.scraper._fetch_rendered_html",
    return_value='<div data-component="ObituaryParagraph">John was beloved.</div>',
)
def test_extract_obituary_data_legacy_uses_paragraph_text(
    mock_fetch: MagicMock, mock_llm: MagicMock
) -> None:
    result = _extract_obituary_data("https://www.legacy.com/person/john-doe-123")
    # For legacy.com, the paragraph text (not full HTML) should be passed to LLM
    llm_call_arg = mock_llm.call_args[0][0]
    assert "<html>" not in llm_call_arg
    assert result["name"] == "John Doe"


# ── get_obituary_info ─────────────────────────────────────────────────────────

_FAKE_SEARCH_HTML = """
<html><body>
<div><div><div><div>
  <article>
    <a href="#">
      <div>
        <div>John Doe</div>
        <span>January 15, 1940 - June 30, 2023</span>
      </div>
      <p>John was a beloved father and community member.</p>
    </a>
    <div>
      <div>
        <a href="https://www.legacy.com/person/john-doe-123">John Doe</a>
        <a href="https://www.legacy.com/person/john-doe-123">details</a>
      </div>
    </div>
  </article>
</div></div></div></div>
</body></html>
"""


@patch("obituary_api.scraper._extract_obituary_data", return_value=_FAKE_LLM_RESPONSE)
@patch("obituary_api.scraper._fetch_rendered_html", return_value=_FAKE_SEARCH_HTML)
def test_get_obituary_info_returns_list(
    mock_fetch: MagicMock, mock_extract: MagicMock
) -> None:
    results = get_obituary_info("John", "Doe", "NJ")
    assert isinstance(results, list)


@patch("obituary_api.scraper._fetch_rendered_html", return_value="<html><body></body></html>")
def test_get_obituary_info_no_results_container_returns_empty(
    mock_fetch: MagicMock,
) -> None:
    """When the selector finds nothing, we get an empty list, not a crash."""
    results = get_obituary_info("Nobody", "Nowhere", "FL")
    assert results == []


def test_get_obituary_info_bad_state_raises() -> None:
    """Passing an unknown state should raise ValueError before any network call."""
    with pytest.raises(ValueError, match="Unknown state"):
        get_obituary_info("John", "Doe", "XX")
