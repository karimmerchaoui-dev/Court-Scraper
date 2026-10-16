"""
FastAPI server — exposes get_obituary_info over HTTP.

Run with:
    python -m obituary_api.server
or via uvicorn:
    uvicorn obituary_api.server:app --host 0.0.0.0 --port 8100
"""
import logging
from typing import Annotated

import pysnooper
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from scraper import get_obituary_info
from state_normaliser import normalise_state

from config import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
"""logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)"""
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Obituary Lookup API",
    description=(
        "Search legacy.com for obituaries by name and US state. "
        "Returns structured records extracted via LLM."
    ),
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Optional bearer-token auth
# ---------------------------------------------------------------------------
_bearer = HTTPBearer(auto_error=False)


def _verify_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
) -> None:
    """If OBITUARY_API_SECRET_KEY is set, require a matching Bearer token."""
    if settings.API_SECRET_KEY is None:
        return  # auth disabled
    if credentials is None or credentials.credentials != settings.API_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing Bearer token.",
        )


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------
class ObituaryRequest(BaseModel):
    first_name: str = Field(..., min_length=1, examples=["Joshua"])
    last_name:  str = Field(..., min_length=1, examples=["Smith"])
    state:      str = Field(
        ...,
        min_length=2,
        examples=["NJ", "New Jersey", "Florida", "FL"],
        description="US state — full name, common alias, or two-letter abbreviation.",
    )


class HeirRecord(BaseModel):
    name: str
    relationship: str


class ObituaryRecord(BaseModel):
    full_name:      str | None
    url:            str | None
    birth_date:     str | None
    death_date:     str | None
    bio:            str | None
    locations:      list[str]
    obituary_text:  str | None
    age:            int | None
    place_of_birth: str | None
    place_of_death: str | None
    friends:        list[str]
    associates:     list[str]
    heirs:          list[HeirRecord]

class ObituaryResponse(BaseModel):
    query: dict
    count: int
    results: list[ObituaryRecord]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["meta"])
def health() -> dict:
    """Simple liveness probe."""
    return {"status": "ok"}


@app.post(
    "/obituaries/search",
    response_model=ObituaryResponse,
    tags=["obituaries"],
    dependencies=[Depends(_verify_token)],
)
@pysnooper.snoop()
def search_obituaries(body: ObituaryRequest) -> ObituaryResponse:
    """
    Search for obituaries by first name, last name, and US state.

    Returns a list of matching records enriched with LLM-extracted fields.
    """
    # Validate state early so we return a 400 before doing any network I/O
    try:
        canonical_state = normalise_state(body.state)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    logger.info(
        "Search request — name: '%s %s', state: '%s' → '%s'",
        body.first_name, body.last_name, body.state, canonical_state,
    )

    try:
        raw_results = get_obituary_info(body.first_name, body.last_name, body.state)
    except Exception as exc:
        logger.error("Scraper error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upstream scraping error: {exc}",
        )

    return ObituaryResponse(
        query={
            "first_name": body.first_name,
            "last_name":  body.last_name,
            "state":      canonical_state,
        },
        count=len(raw_results),
        results=raw_results,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # This block is only reached when running via `python -m obituary_api.server`
    # or through the project-root launcher `run_server.py`.
    uvicorn.run(
        "server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        log_level="info",
    )
