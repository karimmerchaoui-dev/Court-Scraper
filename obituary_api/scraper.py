"""
Core scraping & LLM extraction logic — the heart of the service.

This module is intentionally decoupled from FastAPI so it can be tested
or called from any other Python code without spinning up a web server.
"""
import json
import logging
import os
import time
import traceback

import requests
from bs4 import BeautifulSoup
from requests.exceptions import ReadTimeout, SSLError
from state_normaliser import normalise_state

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mistral schema (structured output)
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT_TEMPLATE = """\
Extract information from the following obituary HTML.

Return ONLY the JSON object matching the provided schema.

Rules:
- Extract only information explicitly supported by the HTML.
- Do not guess or infer missing information.
- Use null for missing scalar values.
- Use [] for missing lists.
- Keep obituary_text as the actual obituary text, without HTML.
- age must be an integer when explicitly stated.
- Dates should be returned as YYYY-MM-DD when the exact date is available.
- If only a partial date is available, preserve the available information rather than inventing it.
- friends should contain names explicitly identified as friends.
- associates should contain people explicitly identified as associates.
- heirs should contain objects with:
  - name: the person's full name
  - relationship: their relationship to the deceased (e.g., "spouse", "son", "daughter", ...)
- Do not put the deceased person's name in friends, associates, or heirs.
- For heirs, if the relationship is not explicitly stated but can be inferred (e.g., "survived by his wife Jane" → spouse), include it.
- If the relationship is unclear, use "family member".

HTML:

{html}
"""

_OBITUARY_SCHEMA = {
    "type": "object",
    "properties": {
        "name":           {"type": ["string", "null"]},
        "obituary_text":  {"type": ["string", "null"]},
        "age":            {"type": ["integer", "null"]},
        "friends":        {"type": "array",  "items": {"type": "string"}},
        "associates":     {"type": "array",  "items": {"type": "string"}},
        "heirs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name":         {"type": "string"},
                    "relationship": {"type": "string"},
                },
                "required": ["name", "relationship"],
                "additionalProperties": False,
            },
        },
        "date_of_death":  {"type": ["string", "null"]},
        "place_of_death": {"type": ["string", "null"]},
        "date_of_birth":  {"type": ["string", "null"]},
        "place_of_birth": {"type": ["string", "null"]},
    },
    "required": [
        "name", "obituary_text", "age", "friends", "associates",
        "heirs", "date_of_death", "place_of_death", "date_of_birth", "place_of_birth",
    ],
    "additionalProperties": False,
}



# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_rendered_html(url: str) -> str:
    """Fetch a URL through Zyte's rendering API and return the browser HTML."""
    while True:
        try:
            response = requests.post(
                "https://api.zyte.com/v1/extract",
                auth=(settings.ZYTE_API_KEY, ""),
                json={"url": url, "browserHtml": True},
                timeout=60,
            )
            response.raise_for_status()
            break
        except ReadTimeout:
            print("Retrying...")
            continue
        except SSLError:
            print("Retrying with unverified HTTPS...")
            response = requests.post(
                "https://api.zyte.com/v1/extract",
                auth=(settings.ZYTE_API_KEY, ""),
                json={"url": url, "browserHtml": True},
                timeout=60,
                verify=False,
            )
            response.raise_for_status()
        except Exception as e:
            traceback.print_exc()
            continue
    return response.json()["browserHtml"]

def _clean_html(html: str) -> str:
    """Strip non-content tags to reduce token usage before LLM extraction."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["img", "select", "button", "script", "style",
                     "svg", "noscript", "iframe", "link", "meta", "head"]):
        tag.decompose()
    return str(soup)


def _extract_legacy_paragraphs(url: str) -> str:
    """Extract raw obituary paragraph text from a legacy.com detail page."""
    html = _fetch_rendered_html(url)
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.find_all(attrs={"data-component": "ObituaryParagraph"})
    return "\n".join(el.get_text().strip() for el in elements)


def _get_configured_llm():
    try:
        from pathlib import Path
        settings_path = Path(__file__).resolve().parent.parent / "court_scraper_basic" / "settings.json"
        if settings_path.exists():
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                obit_cfg = data.get("llm_configs", {}).get("obituary", {}) if isinstance(data.get("llm_configs"), dict) else {}
                svc = obit_cfg.get("service") or data.get("llm_service")
                key = obit_cfg.get("api_key") or data.get("llm_api_key")
                mdl = obit_cfg.get("model") or data.get("llm_model")
                return svc, key, mdl
    except Exception:
        pass
    return None, None, None


def _run_llm_extraction(html_or_text: str, service: str = None, api_key: str = None, model: str = None) -> dict:
    """Send content to LLM (Groq, OpenRouter, Google, or Anthropic) and return the structured obituary dict."""
    conf_svc, conf_key, conf_model = _get_configured_llm()
    svc = (service or conf_svc or "groq").lower().strip()
    key = api_key or conf_key or ""
    mdl = model or conf_model or ""

    prompt = _EXTRACTION_PROMPT_TEMPLATE.format(html=html_or_text)
    system_content = "You are an obituary information extraction engine. Return ONLY valid JSON matching the provided schema."
    
    max_retries = 3
    retry_delay = 1
    
    for attempt in range(max_retries):
        try:
            content = None
            if svc == "openrouter":
                effective_key = key or os.getenv("OPENROUTER_API_KEY", "")
                effective_model = mdl or "anthropic/claude-3.5-haiku"
                import requests as _req
                headers = {
                    "Authorization": f"Bearer {effective_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "http://localhost:8101",
                    "X-Title": "Obituary API",
                }
                body = {
                    "model": effective_model,
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                }
                resp = _req.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=body, timeout=60)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]

            elif svc == "anthropic":
                effective_key = key or os.getenv("ANTHROPIC_API_KEY", "")
                effective_model = mdl or "claude-3-5-haiku-20241022"
                import anthropic as _anthropic
                client = _anthropic.Anthropic(api_key=effective_key)
                msg = client.messages.create(
                    model=effective_model,
                    max_tokens=4096,
                    system=system_content,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                content = msg.content[0].text

            elif svc in ("google", "gemini"):
                effective_key = key or os.getenv("GEMINI_API_KEY", "")
                effective_model = mdl or "gemini-2.0-flash"
                import requests as _req
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{effective_model}:generateContent?key={effective_key}"
                headers = {"Content-Type": "application/json"}
                body = {
                    "contents": [{"parts": [{"text": f"{system_content}\n\n{prompt}"}]}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}
                }
                resp = _req.post(url, headers=headers, json=body, timeout=60)
                resp.raise_for_status()
                content = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

            else:  # Default: Groq
                effective_key = key or os.getenv("GROQ_API_KEY", "")
                effective_model = mdl or "openai/gpt-oss-120b"
                from groq import Groq
                client = Groq(api_key=effective_key)
                completion = client.chat.completions.create(
                    model=effective_model,
                    messages=[
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0,
                    max_tokens=4096,
                    response_format={"type": "json_object", "schema": _OBITUARY_SCHEMA}
                )
                content = completion.choices[0].message.content
            
            # Clean the response if needed
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON
            result = json.loads(content)
            
            # Optional: Validate against schema
            # Validate required fields are present
            required_fields = _OBITUARY_SCHEMA["required"]
            for field in required_fields:
                if field not in result:
                    print(f"⚠️ Missing field in response: {field}")
                    # Fill missing with default values
                    if field in _OBITUARY_SCHEMA["properties"]:
                        prop = _OBITUARY_SCHEMA["properties"][field]
                        if prop.get("type") == "array" or "array" in str(prop.get("type")):
                            result[field] = []
                        else:
                            result[field] = None
            
            # Record cost
            try:
                from court_scraper_basic.ai.llm_cost_tracker import record_llm_cost
                tokens_in = len(prompt) // 4
                tokens_out = len(content) // 4
                record_llm_cost("obituary", effective_model, tokens_in, tokens_out, service=svc)
            except Exception:
                pass

            return result
            
        except json.JSONDecodeError as e:
            print(f"Groq returned invalid JSON (attempt {attempt + 1}): {e}")
            print(f"Raw response: {content[:200]}...")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                # Return empty schema on final failure
                return {
                    "name": None,
                    "obituary_text": None,
                    "age": None,
                    "friends": [],
                    "associates": [],
                    "heirs": [],
                    "date_of_death": None,
                    "place_of_death": None,
                    "date_of_birth": None,
                    "place_of_birth": None,
                }
                
        except Exception as e:
            print(f"Groq extraction failed (attempt {attempt + 1}): {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                # Return empty schema on final failure
                return {
                    "name": None,
                    "obituary_text": None,
                    "age": None,
                    "friends": [],
                    "associates": [],
                    "heirs": [],
                    "date_of_death": None,
                    "place_of_death": None,
                    "date_of_birth": None,
                    "place_of_birth": None,
                }


def _extract_obituary_data(url: str,obituary_snippet: str) -> dict:
    """Full pipeline: fetch → clean → LLM extract for a single obituary URL."""
    if "legacy.com" in url or "obits.nj" in url:
        text = _extract_legacy_paragraphs(url)
        if not text:
            text = obituary_snippet
        # For legacy.com we pass the paragraph text directly (already stripped)
        data = _run_llm_extraction(text)
    else:
        html = _fetch_rendered_html(url)
        cleaned = _clean_html(html)
        if not cleaned:
            cleaned = obituary_snippet
        data = _run_llm_extraction(cleaned)
    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_obituary_info(first_name: str, last_name: str, state: str) -> list[dict]:
    """
    Search legacy.com for obituaries matching *first_name* + *last_name* in
    *state*, extract detailed information via LLM for each result, and return
    a list of structured obituary records.

    Args:
        first_name: Person's first name.
        last_name:  Person's last name.
        state:      US state as a full name, common alias, or two-letter code
                    (e.g. "NJ", "new jersey", "Jersey").

    Returns:
        List of dicts, each containing:
            full_name, url, person_id, birth_date, death_date, bio,
            locations, obituary_text, age, place_of_birth, place_of_death,
            friends, associates, heirs
    """
    canonical_state = normalise_state(state)
    url_state = canonical_state.replace(" ", "+")

    search_url = (
        f"https://www.legacy.com/obituaries/search"
        f"?query={first_name.replace(' ','+')}+{last_name.replace(' ','+')}"
        f"&country=United+States"
        f"&state={url_state}"
    )

    logger.info("Fetching search results from: %s", search_url)
    browser_html = _fetch_rendered_html(search_url)
    soup = BeautifulSoup(browser_html, "html.parser")

    main_results = soup.select_one(
        "body > div:nth-of-type(5) > div:nth-of-type(2) > "
        "div:nth-of-type(2) > div:nth-of-type(1)"
    )
    if main_results is None:
        logger.warning("Could not locate results container in search page.")
        return []

    articles = main_results.find_all("article")
    logger.info("Found %d article(s) in search results.", len(articles))

    results: list[dict] = []

    for article in articles:
        try:
            name = (
                article.select_one("a")
                .select_one("div")
                .select_one("div")
                .get_text()
            )
            date_birth_death = (
                article.select_one("a")
                .select_one("div")
                .select_one("span")
                .get_text()
            )
            obituary_snippet = (
                article.select_one("a").select_one("p").get_text()
            )

            undercard = article.select_one("div").select_one("div")
            children = undercard.find_all(recursive=False)
            link_tag = children[1].find(href=True)
            obituary_url: str = link_tag.get("href")

            birth_date: str | None = None
            death_date: str | None = None
            if "-" in date_birth_death:
                parts = date_birth_death.split("-", 1)
                birth_date = parts[0].strip()
                death_date = parts[1].strip()

            logger.info("Extracting data for '%s' from %s", name, obituary_url)
            extracted = _extract_obituary_data(obituary_url,obituary_snippet)
            print(f"extracted.get : {extracted.get("obituary_text")}")
            results.append({
                "full_name":      name,
                "url":            obituary_url,
                "birth_date":     extracted.get("date_of_birth") or birth_date,
                "death_date":     extracted.get("date_of_death") or death_date,
                "bio":            extracted.get("obituary_text") or obituary_snippet,
                "locations":      [canonical_state],
                "obituary_text":  extracted.get("obituary_text"),
                "age":            extracted.get("age"),
                "place_of_birth": extracted.get("place_of_birth"),
                "place_of_death": extracted.get("place_of_death"),
                "friends":        extracted.get("friends", []),
                "associates":     extracted.get("associates", []),
                "heirs":          extracted.get("heirs", []),
            })

        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to process article: %s", exc, exc_info=True)
            continue

    return results
