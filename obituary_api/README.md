# 🕯️ Obituary Lookup API

> A self-hosted REST API that searches **legacy.com** for obituary records by name and US state, enriches each result with LLM-extracted structured data, and returns clean, ready-to-use JSON.

---

## 🛠️ Technologies

| Layer | Tool / Library |
|---|---|
| **Language** | Python 3.11+ |
| **Web Framework** | [FastAPI](https://fastapi.tiangolo.com/) + [Uvicorn](https://www.uvicorn.org/) |
| **HTML Rendering** | [Zyte API](https://www.zyte.com/) (headless browser rendering) |
| **HTML Parsing** | [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) |
| **LLM Extraction** | [Groq](https://groq.com/) · [Mistral AI](https://mistral.ai/) · [Google Gemini](https://ai.google.dev/) · [Anthropic Claude](https://www.anthropic.com/) · [OpenRouter](https://openrouter.ai/) |
| **HTTP Client** | [Requests](https://docs.python-requests.org/) |
| **Config** | [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) + `.env` |
| **Auth** | Optional Bearer token via FastAPI `HTTPBearer` |

---

## ✨ Features

- 🔍 **Name + State search** — Query obituaries by first name, last name, and any US state (full name, abbreviation, or common alias like `"Jersey"` → New Jersey).
- 🌐 **Headless browser scraping** — Uses Zyte's rendering API to handle JavaScript-heavy pages that a simple `requests.get()` can't reach.
- 🧹 **Smart HTML cleaning** — Strips scripts, styles, images, and all non-content tags before feeding the page to the LLM, drastically reducing token usage.
- 🤖 **Multi-provider LLM extraction** — Configurable to use Groq, Mistral, Google Gemini, Anthropic, or OpenRouter. Just swap a setting, no code changes needed.
- 📐 **Structured JSON output** — Every obituary is returned with a strict, validated schema:
  - Name, age, obituary text
  - Date & place of birth / death
  - Friends, associates
  - **Heirs** with their relationship to the deceased (spouse, son, daughter, etc.)
- 🔄 **Retry logic** — Automatic retries with exponential back-off on timeouts, SSL errors, and malformed LLM responses.
- 🔒 **Optional Bearer token auth** — Protect the endpoint with a secret key; disabled by default for easy local use.
- 📄 **Auto-generated API docs** — FastAPI ships with Swagger UI at `/docs` and ReDoc at `/redoc` out of the box.
- 🏥 **Health check endpoint** — `GET /health` for liveness probes and uptime monitoring.
- 🗂️ **Standalone client module** — `client.py` can be imported into any Python project or called directly from the CLI.

---

## 🗂️ Project Structure

```
obituary_api/
├── __init__.py           # Package marker
├── config.py             # Settings loaded from .env
├── state_normaliser.py   # Full US state alias → canonical name map
├── scraper.py            # Core scraping + LLM extraction logic
├── server.py             # FastAPI app & endpoint definitions
└── client.py             # Standalone HTTP client / mini-SDK
```

---

## ⚙️ Setup

### 1 — Install dependencies

```bash
pip install fastapi uvicorn[standard] requests beautifulsoup4 mistralai groq python-dotenv pydantic-settings
```

### 2 — Configure `.env`

```dotenv
ZYTE_API_KEY=...                   # Zyte rendering API key
MISTRAL_API_KEY=...                # Mistral AI key (optional if using another provider)
MISTRAL_MODEL=mistral-small-latest

OBITUARY_API_HOST=0.0.0.0
OBITUARY_API_PORT=8100

# Optional — uncomment to protect the endpoint with a Bearer token:
# OBITUARY_API_SECRET_KEY=change-me-to-a-strong-random-value
```

### 3 — Run the server

```bash
# From the project root
python -m obituary_api.server

# Or with uvicorn directly
uvicorn obituary_api.server:app --host 0.0.0.0 --port 8100
```

Interactive docs → **http://localhost:8100/docs**

---

## 📡 API Reference

### `POST /obituaries/search`

**Request body:**
```json
{
  "first_name": "Joshua",
  "last_name":  "Smith",
  "state":      "NJ"
}
```

**Response:**
```json
{
  "query":   { "first_name": "Joshua", "last_name": "Smith", "state": "New Jersey" },
  "count":   1,
  "results": [
    {
      "full_name":      "Joshua T. Smith",
      "url":            "https://www.legacy.com/...",
      "birth_date":     "1945-03-12",
      "death_date":     "2024-11-01",
      "bio":            "Joshua T. Smith passed away …",
      "locations":      ["New Jersey"],
      "obituary_text":  "Full obituary text …",
      "age":            79,
      "place_of_birth": "Newark, NJ",
      "place_of_death": "Trenton, NJ",
      "friends":        ["Robert Brown"],
      "associates":     [],
      "heirs": [
        { "name": "Jane Smith",    "relationship": "spouse" },
        { "name": "Michael Smith", "relationship": "son" }
      ]
    }
  ]
}
```

### `GET /health`

Returns `{"status": "ok"}` — use as a liveness probe.

---

## 🧑‍💻 Using the Client

```python
from client import search_obituaries

results = search_obituaries("Joshua", "Smith", "NJ")

for r in results:
    print(r["full_name"], r["death_date"])
    for heir in r["heirs"]:
        print(f"  ↳ {heir['name']} ({heir['relationship']})")
```

Or from the command line:

```bash
python client.py
```

---

## 🍳 The Process — How It Was Cooked

This project didn't start as what it is now. It evolved organically through several distinct phases:

### Phase 1 — The Basic Scraper
It started as a plain Python script: `requests.get()` a page, parse the HTML with BeautifulSoup, pull out the data you want. Simple, fast, works fine for static pages. That's where anyone starts.

### Phase 2 — Multi-Page & Multi-Site Scraping
The first wall hit quickly — search result pages return multiple entries, each linking to its own detail page. The scraper had to follow those links, loop through paginated results, and handle subtle differences between page layouts across different obituary websites (legacy.com, obits.nj.com, etc.). Suddenly the code had to be smarter about URL construction, HTML selectors, and error handling per site.

### Phase 3 — Headless Browser Rendering
Static scraping broke completely on JavaScript-rendered pages. The HTML returned by `requests.get()` was an empty shell — all the real content was injected by client-side JS. The solution was Zyte's rendering API: send a URL, get back the full browser HTML as if a real browser had loaded the page. This unlocked every target site.

### Phase 4 — LLM-Powered Text Extraction
Even with the full HTML in hand, parsing obituary text with CSS selectors was fragile — every site had a different structure. The pivot: pass the raw obituary text to an LLM with a strict JSON schema and let it extract names, dates, places, relationships. The model handles ambiguity, varied formats, and implicit relationships (e.g., *"survived by his wife Jane"* → `{ name: "Jane", relationship: "spouse" }`).

### Phase 5 — Full-Page LLM Analysis with Smart Cleaning
The final evolution: instead of targeting specific CSS selectors, the scraper now grabs the entire rendered page, strips all the noise (scripts, styles, nav, footers, images) with BeautifulSoup, and feeds the clean content straight to the LLM. The model figures out what's relevant. This made the pipeline dramatically more robust — no more brittle selectors breaking every time a website updates its layout.

---

## 📚 What I Learned

If you come into this project knowing only the basics of Python and having done a simple scraper or two, here is what you will genuinely walk away understanding:

- **How modern websites actually work** — the difference between server-rendered and client-rendered HTML, and why `requests.get()` often returns an empty page.
- **How to use a headless browser API** (Zyte) to get the real DOM, and why this is essential for any serious scraping project.
- **How to navigate real-world HTML** — working with messy, inconsistent page structures using BeautifulSoup selectors, and why you can't always rely on clean class names.
- **How to chain multiple HTTP requests** — fetching a search page, extracting result URLs, then fetching each detail page in a loop.
- **How to handle failures gracefully** — timeouts, SSL errors, missing elements, empty responses. Real scraping is full of edge cases; retry logic and `try/except` blocks are not optional.
- **How to structure a prompt for an LLM** — giving clear rules, specifying what `null` means, defining a JSON schema, and constraining the model's output to exactly what you need.
- **How LLMs can replace fragile parsers** — instead of writing a new CSS selector every time a site changes, you describe what you want in plain English and let the model handle variation.
- **How to build a REST API with FastAPI** — request validation with Pydantic, response models, dependency injection for auth, auto-generated docs.
- **How to separate concerns cleanly** — keeping scraping logic (`scraper.py`) decoupled from the web server (`server.py`) so it can be tested or reused independently.
- **How to manage configuration** — using `.env` files and Pydantic settings instead of hardcoding secrets.
- **How to think about token costs** — understanding that you can't just dump raw HTML into an LLM and that preprocessing (cleaning) is essential for both cost and accuracy.

---

## 🚀 How It Can Be Improved

This project has a solid foundation. Here's where it can go next:

- **Multi-site support** — Add adapters for more obituary websites (findagrave.com, tributes.com, obits.com, local newspaper archives). A plugin-style architecture would let each site have its own fetch + clean strategy.
- **Richer deceased person analysis** — Run additional LLM passes to infer demographics, profession, community ties, or cause of death when the text supports it.
- **Extended data extraction** — Pull more fields when available: maiden names, military service, religious affiliations, charitable organizations mentioned.
- **Heir contact enrichment** — Cross-reference heir names against public records, LinkedIn, or people-search databases to surface contact information (phone, email, address) for the next of kin.
- **Async & parallel scraping** — Replace the sequential loop with `asyncio` + `httpx` to process multiple obituaries concurrently and cut total run time dramatically.
- **Persistent storage** — Save results to a database (PostgreSQL, SQLite) instead of returning everything in a single HTTP response. Add endpoints for querying historical records.
- **Webhook / callback support** — For long-running searches, return a job ID immediately and push results to a callback URL when ready.
- **Caching** — Cache Zyte renders and LLM responses for repeated queries on the same URL to save API costs.
- **Monitoring & cost tracking** — Expose LLM token usage and Zyte API call counts per request so you can measure and optimize costs over time.
