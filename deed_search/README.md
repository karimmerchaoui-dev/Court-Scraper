# Deed Search

**Automated county deed & property-record retrieval engine, exposed as a hosted HTTP API.**

Deed Search logs into county recorder / clerk-of-court websites, searches for a deed by **book & page**, **instrument number**, or **grantor/grantee name**, extracts the record's metadata, and optionally downloads the document itself — all without a human clicking through a county's website by hand.

---

## Overview

Every county in the U.S. publishes property deed records online, but there is no shared format, no shared API, and often no meaningful search tooling beyond a decades-old ASP.NET form. Finding a specific deed — or worse, finding *every* deed tied to a name across a dozen counties — means a person manually operating a different, clunky website for each jurisdiction, re-entering the same search over and over, and manually saving whatever comes back.

**This project solves the problem of turning that manual, repetitive, county-by-county lookup process into a single, consistent, programmatic operation.** One function call — or one HTTP request — takes a county name plus a book/page, instrument number, or name, and returns structured deed data (and, optionally, the document itself), regardless of which of the 13 supported county websites is actually behind it. The engine absorbs each county's quirks (different HTML, different search flows, different iframes) so the caller never has to think about them.

## Who Would Benefit from This Tool

- **Real estate lead-generation teams** who need to pull ownership/transaction history at scale across many counties without hiring someone to do it by hand.
- **Title and abstract companies** doing chain-of-title research who need fast, repeatable deed lookups.
- **Skip tracers and process servers** who use deed records to locate current property owners.
- **Investors and wholesalers** screening properties or building lead lists based on recent deed activity (sales, foreclosures, transfers).
- **Legal teams / paralegals** who need to attach a specific recorded deed to a case file.
- **Data teams** who want deed metadata flowing into a database or CRM automatically instead of via manual entry.

## Key Features

- **One consistent interface across many counties.** Search by book/page, instrument number, or grantor/grantee name — the underlying county-specific navigation, form-filling, and result parsing is handled transparently.
- **Metadata extraction, not just file downloads.** Every match can return structured data (grantor, grantee, book/page, recording date, etc.) even if you don't need the actual document.
- **Optional document download**, with automatic file renaming to a predictable, collision-safe naming pattern.
- **Block/lot filtering** on counties whose sites support it, to narrow large result sets.
- **Remote, cloud-hostable HTTP API** with job-based async processing (so long-running scrapes never time out a client or proxy) plus a synchronous endpoint for quick lookups.
- **API-key authentication** and per-job sandboxed output directories, so concurrent requests from different callers never collide or leak each other's files.
- **Extensible by design.** Adding a new county is almost entirely declarative (XPaths + a couple of small helper functions) — the shared scraping engine handles retries, iframes, downloads, and file management for every county automatically.
- **CLI, programmatic Python API, and REST API** — use whichever fits: a quick terminal lookup, an import in your own Python code, or a remote call from any language.

## Technologies Used

| Layer | Technology |
|---|---|
| Browser automation | [SeleniumBase](https://seleniumbase.io/) (Selenium WebDriver + built-in anti-bot handling) |
| HTML parsing | BeautifulSoup4 |
| REST API | Flask, served in production via Gunicorn |
| Concurrency | Python `concurrent.futures.ThreadPoolExecutor` (job-based background processing) |
| CLI | Python `argparse` |
| Data model | Python `dataclasses` + `enum` |
| Optional OCR fallback | Windows OCR API (`winrt`), OpenCV, `pdfplumber`, `pdf2image` |
| Language | Python 3.10+ |

## Project Background

Deed Search was originally built in **August 2025** while working for **MSV Properties**, a real-estate company, to generate real estate leads. The company needed a reliable way to pull property and ownership data straight from county recorder websites — at the volume and speed a manual process couldn't sustain — to feed its lead pipeline. What started as a single-county scraper grew into a general-purpose engine supporting more than a dozen New Jersey and Florida counties, with a shared architecture that made adding new counties fast rather than a one-off rebuild each time.

## Technical Details

### Architecture

```
Client (HTTP/CLI/Python)
        │
        ▼
   server.py  (Flask REST API — job queue, auth, file serving)
        │
        ▼
   main.py    (download_deed() — the public programmatic entry point)
        │
        ▼
 downloader.py (DeedDownloader — the shared, county-agnostic engine:
                open form → search → iterate rows → extract → download)
        │
        ▼
county_config.py (CountyConfig schema + central registry)
        │
        ▼
 counties/*.py  (One file per county: URLs, XPaths, small per-site
                 helper functions — everything that differs by county)
```

Supporting modules used throughout the pipeline:
- **`browser_helpers.py`** — iframe-safe element lookup, HTML-table-to-dict parsing
- **`download_manager.py`** — detects, waits for, and safely renames downloaded files

The core idea: **one shared engine, many thin configs.** `DeedDownloader` contains all the logic that's the same everywhere (retry handling, waiting for downloads, iterating result rows, renaming files). Each county is just a `CountyConfig` — a declarative description of its URLs, form field XPaths, and a handful of small callback functions for anything genuinely site-specific (opening a result's detail page, triggering the actual file download, filtering by block/lot). Adding a county almost never requires touching the engine itself.

### Supported counties

13 counties are currently active (registered and searchable): **Ocean, Essex, Sussex, Atlantic, Bergen, Burlington, Camden, Middlesex, Mercer, Cape May, and Gloucester** counties (New Jersey), plus **Volusia and Osceola** counties (Florida).

Every active county supports **book/page** and **name** search. Several also support **block/lot** result filtering. Instrument-number search is currently fully wired for Volusia County only — most New Jersey counties have the instrument search form fields configured but are missing the dedicated URL that mode needs, so instrument search on those counties needs that one field filled in before it's usable (see the note at the top of each affected county's config).

Additional county configs exist in the codebase but aren't yet activated (Brevard, Broward, Cumberland, Duval, Hudson, Monmouth, Morris, Passaic, Polk, Seminole, and Union counties) — they were written but not yet verified against the live site, and can be turned on by adding their module name to `counties/__init__.py`.

### Request model

Every lookup is described by a `DeedRequest`:

```python
DeedRequest(
    book=None, page=None,               # BOOK_PAGE search
    instrument=None,                     # INSTRUMENT search
    first_name=None, last_name=None,     # NAME search
    block=None, lot=None,                # optional result filtering
    deed_type=None,                      # override county's default deed type(s)
    download_file=False,                 # False = extract metadata only
    case_number=None,                    # optional external record-sync key
    search_mode_override=None,           # force a specific mode instead of auto-inferring
)
```

If `search_mode_override` isn't set, the mode is inferred: an `instrument` value wins, otherwise a `first_name`/`last_name` value wins, otherwise it falls back to book/page.

### Deployment model

The scraper is CPU/RAM-heavier than a typical web service, since every job drives a real Chrome browser. The REST API (`server.py`) is designed to be hosted on a single cloud instance (or container) with Chrome installed, and is called over HTTPS from anywhere — the caller never needs Python, Selenium, or a browser locally. Because a scrape can take anywhere from seconds to minutes, the primary API flow is **job-based**: submit a request, get a `job_id` back immediately, and poll for the result. A synchronous convenience endpoint also exists for quick lookups behind a generous timeout.

## Installation

### Requirements

- Python 3.10+
- Google Chrome (SeleniumBase drives a real Chrome browser)

### Setup

```bash
git clone <this-repository>
cd deed_search

pip install seleniumbase selenium flask requests beautifulsoup4
```

> There is no committed `requirements.txt` yet — the above covers everything the core engine and API need. The optional OCR fallback (`ocr.py`, Windows-only, not part of the main pipeline) additionally needs `opencv-python`, `numpy`, `pdfplumber`, `pdf2image`, `tqdm`, and `winrt`.

### Running a single lookup (CLI)

```bash
python main.py --county "Gloucester County" --book 1234 --page 56

# Visible browser, useful while debugging a county's XPaths
python main.py --county "Gloucester County" --book 1234 --page 56 --no-headless

# Search by name instead
python main.py --county "Gloucester County" --first-name Robert --last-name Anderson --search-mode NAME

# List every registered county
python main.py --list-counties
```

### Using it as a library

```python
from deed_search.main import download_deed

result = download_deed(
    county_name="gloucester county",
    output_dir="deed_output",
    first_name="Robert",
    last_name="Anderson",
    search_mode="NAME",
    block="181.02",
    download_file=False,
)

if result["success"]:
    print("Downloaded to:", result["file_path"])
    print("Extracted data:", result["extracted_data"])
else:
    print("Failed:", result["error"])
```

### Running the hosted API

```bash
export DEED_API_KEY="some-long-random-secret"
python server.py                      # development
# or, in production:
gunicorn -w 1 --threads 8 -b 0.0.0.0:8000 server:app
```

Calling it remotely (see `deed_api.py` for a small reusable client helper):

```python
import time, requests

BASE_URL = "https://your-server-address.example.com"
headers = {"X-API-Key": "some-long-random-secret"}

resp = requests.post(f"{BASE_URL}/api/deeds", headers=headers, json={
    "county_name": "essex county",
    "book": "1",
    "page": "2000",
    "download_file": False,
})
job_id = resp.json()["job_id"]

while True:
    status = requests.get(f"{BASE_URL}/api/deeds/{job_id}", headers=headers).json()
    if status["status"] in ("done", "error"):
        break
    time.sleep(2)

print(status["result"] if status["status"] == "done" else status["error"])
```

## Output Examples

**A metadata-only lookup** (`download_file=False`) returns structured deed data without saving anything to disk:

```python
{
    "success": True,
    "file_path": None,
    "error": None,
    "county": "gloucester county",
    "book": "None",
    "page": "None",
    "extracted_data": [
        {
            "grantor": "Anderson, Robert",
            "grantee": "Smith, Jane",
            "book": "1234",
            "page": "56",
            "recording_date": "2024-03-11",
            "deed_type": "Warranty Deed",
            "file_name": "Warranty Deed_2026-08-13 09:41:02.311"
        }
    ],
}
```

**A full download** (`download_file=True`) additionally saves the document and returns its path:

```python
{
    "success": True,
    "file_path": "deed_output/deeds/2026-08-13_09-41-02/book_1234_page_56_row_1.pdf",
    "error": None,
    "county": "essex county",
    "book": "1234",
    "page": "56",
    "extracted_data": None,
}
```

**A failed lookup** (e.g. an unregistered county name):

```python
{
    "success": False,
    "file_path": None,
    "error": "County 'made-up county' not found. Available: ['ocean_county', 'essex_county', ...]",
    "county": "made-up county",
    "book": "None",
    "page": "None",
}
```

---

## What's Worth Writing Tests For

There's currently no automated test suite — `test.py` is a manual smoke-test script that opens a real browser against a live county site. That's valuable for verifying a county still works, but it's slow, flaky (depends on an external site being up and unchanged), and not something you'd want running in CI. Priority order for adding real (`pytest`) coverage:

1. **`DeedRequest.search_mode` inference** — pure logic, zero I/O, easy to get 100% coverage on. Test that an `instrument` value wins over a name, a name wins over book/page, book/page is the fallback, and that `search_mode_override` always wins regardless of what else is populated. This is exactly the kind of logic that's silently broken before (see the fix applied during this cleanup) and is cheap to protect going forward.

2. **`parse_search_mode()`** — string-to-enum conversion used by both the CLI and the API. Test valid values (including case-insensitivity, e.g. `"name"` vs `"NAME"`), `None` passthrough, and that an invalid string raises `ValueError` with a helpful message.

3. **`county_config.registry`** — registration and lookup. Test that a registered county is retrievable by name (case-insensitively, with/without spaces), and that looking up an unregistered name raises a clear, catchable error (this is the exact failure mode `download_deed()` depends on to build its "county not found" message).

4. **`DownloadManager._sanitize_filename` and the extension-preserving logic in `rename_file`** — pure string logic that's easy to unit test without touching a browser: invalid filename characters get stripped, the renamed file keeps the *source* file's real extension regardless of what the caller passed in, and a caller-supplied name that already has an extension doesn't end up double-extensioned.

5. **`browser_helpers.html_table_to_dict`** — feed it small, hand-crafted HTML fixtures (a simple key/value row, a multi-`<div>` cell that should become a list, a `book_page` cell that should get split into separate `book`/`page` keys) and assert on the resulting dict. No browser needed at all, and this function is shared by every county's metadata extraction.

6. **`server.py`'s request-building logic (`_build_kwargs`)** — test that a missing `county_name` is rejected with a 400, that `output_dir`/`headless` sent by a client are always overridden rather than trusted, and that an invalid `search_mode` string produces a 400 with a useful message. Flask's test client makes this straightforward without needing a live server or real scraping.

7. **Job lifecycle in `server.py`** — with `download_deed` mocked out (so no real browser runs), test that `POST /api/deeds` returns `202` with a `job_id`, that `GET /api/deeds/<id>` reflects `pending` → `done`/`error` correctly, and that an unknown `job_id` returns `404`. This protects the async job contract every client depends on without needing Selenium or a real county site in CI at all.

What's *not* worth investing in right now: per-county XPath/scraping tests. Those inherently require either a live browser hitting a real (and occasionally-changing) county website, or a maintained local mirror of each site's HTML — both are expensive to build and keep in sync, and a scraping break is usually easier to catch and fix in the moment (`--no-headless` + watch it run) than to encode as an automated assertion against a page structure the county could quietly change at any time.
