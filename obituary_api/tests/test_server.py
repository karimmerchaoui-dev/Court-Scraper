"""
Tests for the FastAPI server using FastAPI's built-in TestClient.

All external calls (Zyte API, Mistral) are mocked — these tests run
instantly with no network access and no API credits consumed.
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Add the parent directory to sys.path to allow importing state_normaliser
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from server import app

client = TestClient(app)


# ── /health ───────────────────────────────────────────────────────────────────

def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ── /obituaries/search — input validation ─────────────────────────────────────

def test_search_missing_fields_returns_422() -> None:
    """Missing required fields → Pydantic validation error."""
    response = client.post("/obituaries/search", json={})
    assert response.status_code == 422


def test_search_unknown_state_returns_400() -> None:
    response = client.post("/obituaries/search", json={
        "first_name": "John",
        "last_name":  "Doe",
        "state":      "XX",   # not a US state
    })
    assert response.status_code == 400
    assert "Unknown state" in response.json()["detail"]


# ── /obituaries/search — happy path (fully mocked) ────────────────────────────

_MOCK_RESULT = {
    "full_name":      "John Doe",
    "url":            "https://www.legacy.com/obituaries/john-doe",
    "person_id":      None,
    "birth_date":     "1940-01-15",
    "death_date":     "2023-06-30",
    "bio":            "John was a beloved father.",
    "locations":      ["New Jersey"],
    "obituary_text":  "John was a beloved father.",
    "age":            83,
    "place_of_birth": "Newark, NJ",
    "place_of_death": "Trenton, NJ",
    "friends":        ["Mike Johnson"],
    "associates":     [],
    "heirs": [
        {"name": "Jane Doe",   "relationship": "spouse"},
        {"name": "Tom Doe",    "relationship": "son"},
    ],
}


@patch("obituary_api.server.get_obituary_info", return_value=[_MOCK_RESULT])
def test_search_happy_path(mock_scraper: MagicMock) -> None:
    response = client.post("/obituaries/search", json={
        "first_name": "John",
        "last_name":  "Doe",
        "state":      "NJ",
    })
    assert response.status_code == 200
    body = response.json()

    assert body["count"] == 1
    assert body["query"]["state"] == "New Jersey"   # normalised

    result = body["results"][0]
    assert result["full_name"] == "John Doe"
    assert result["age"] == 83
    assert len(result["heirs"]) == 2
    assert result["heirs"][0]["relationship"] == "spouse"

    # Confirm the scraper was called with the right arguments
    mock_scraper.assert_called_once_with("John", "Doe", "NJ")


@patch("obituary_api.server.get_obituary_info", return_value=[])
def test_search_no_results(mock_scraper: MagicMock) -> None:
    response = client.post("/obituaries/search", json={
        "first_name": "Nobody",
        "last_name":  "Nowhere",
        "state":      "FL",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["results"] == []


@patch("obituary_api.server.get_obituary_info", side_effect=RuntimeError("Zyte timeout"))
def test_search_scraper_error_returns_502(mock_scraper: MagicMock) -> None:
    response = client.post("/obituaries/search", json={
        "first_name": "John",
        "last_name":  "Doe",
        "state":      "NJ",
    })
    assert response.status_code == 502
    assert "Zyte timeout" in response.json()["detail"]


# ── State aliases accepted by the endpoint ────────────────────────────────────

@pytest.mark.parametrize("state_input, expected_canonical", [
    ("NJ",         "New Jersey"),
    ("new jersey", "New Jersey"),
    ("Jersey",     "New Jersey"),
    ("FL",         "Florida"),
    ("florida",    "Florida"),
])
@patch("obituary_api.server.get_obituary_info", return_value=[])
def test_search_state_normalisation(
    mock_scraper: MagicMock,
    state_input: str,
    expected_canonical: str,
) -> None:
    response = client.post("/obituaries/search", json={
        "first_name": "Test",
        "last_name":  "User",
        "state":      state_input,
    })
    assert response.status_code == 200
    assert response.json()["query"]["state"] == expected_canonical
