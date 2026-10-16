# Court-Scraper

A distributed multi-state court automation and intelligence platform that extracts legal case documents across **all 21 New Jersey counties** and **15 Florida counties**, enriches them with property deeds and deceased-person records, and syncs full lifecycle state to a Supabase PostgreSQL database with a real-time web dashboard.

Built for high-volume, anti-bot-resilient scraping with **Selenium 4 + Undetected-Chromedriver**, containerized under **Docker + Xvfb virtual displays**, backed by an **ACID-compliant SQLite durable task queue**, and tested with a **180+ automated unit & integration test suite**.

---

## Architecture & Technology Stack

```
                          ┌──────────────────────────────────────────────┐
                          │         Web GUI / Real-Time Dashboard        │
                          │        (Flask + Flask-SocketIO + HTML5)      │
                          └──────────────────────┬───────────────────────┘
                                                 │
                                                 ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 CORE ENGINE (main.py)                                  │
│                                                                                        │
│   ┌───────────────────────────┐                    ┌───────────────────────────────┐   │
│   │   Orchestrator Pipeline   │                    │     Durable Task Queue        │   │
│   │  (5-8 Stages, Auto-Retry) │                    │ (SQLite WAL-mode: deed_queue) │   │
│   └─────────────┬─────────────┘                    └───────────────┬───────────────┘   │
│                 │                                                  │                   │
│   ┌─────────────▼─────────────┐                    ┌───────────────▼───────────────┐   │
│   │   Browser Driver Pool     │                    │     Deed Worker Processes     │   │
│   │ (Undetected-Chromedriver  │                    │ (Apify + Groq LLaMA-3.3-70B   │   │
│   │  + Xvfb Virtual Displays) │                    │  Property Ownership Extract)  │   │
│   └─────────────┬─────────────┘                    └───────────────┬───────────────┘   │
└─────────────────┼──────────────────────────────────────────────────┼───────────────────┘
                  │                                                  │
                  ▼                                                  ▼
┌───────────────────────────────────┐              ┌─────────────────────────────────────┐
│      External Enrichment APIs     │              │           Data Persistence          │
│  - SalesWeb NJ (bs4 HTML Parser)  │              │  - Supabase (PostgreSQL + RPCs)     │
│  - Zillow API (Apify)             │              │  - Local Excel / Report Exporters   │
│  - Obituary Search Microservice   │              │  - Docker Volume Mounts (PDF store) │
└───────────────────────────────────┘              └─────────────────────────────────────┘
```

| Component | Technology | Description |
|---|---|---|
| **Core Engine** | Python 3.12 | Type-annotated, modular pipeline architecture with async event dispatching |
| **Containerization** | Docker, Docker Compose, Xvfb | Headed browser execution under virtual framebuffers (`DISPLAY=:99`, `shm_size: 2GB`) |
| **Durable Job Queue** | SQLite (WAL Mode, Multi-Threaded) | Crash-resilient queue with automatic in-flight job recovery, retries, and FIFO scheduling |
| **Browser Automation** | Selenium 4, Undetected-Chromedriver | Anti-bot evasion, custom wait conditions, tab recycling, and human-like interactions |
| **Web Dashboard** | Flask, Flask-SocketIO, WebSockets | Real-time case tracking, stage telemetry (`PENDING` → `RUNNING` → `SUCCESS`), log streaming |
| **AI / Document Extraction** | Groq LLaMA 3.3, Anthropic Claude | OCR & LLM extraction for complaints, final judgments, and bankruptcy filings |
| **Database & Persistence** | Supabase (PostgreSQL), openpyxl | Relational schema, RPC stored procedures, soft-deletes, and Excel batch reports |
| **Testing & Quality** | pytest (180+ tests) | Isolated unit & integration tests (`tmp_path`, in-memory DBs, zero Selenium mocks) |
| **Network & Proxies** | NordVPN CLI, Brightdata Residential | Automatic IP rotation with debounced leader-election reset cycles |

---

## Key Platform Capabilities

### 1. Robust Pipeline Architecture
Every court case is processed through a structured, decoupled sequence of stages called **Pipeline Blocks**:
* **Pre-Check Stage**: Evaluates cases against SalesWeb auction databases and Zillow Zestimates to filter ineligible properties before spinning up browser instances.
* **Navigation & Authentication**: Multi-account rotation with session recovery and CAPTCHA handling.
* **Intelligent File Picking**: Heuristic regex scanner that targets critical legal documents (complaints, lis pendens, dismissals, final judgments, orders to vacate, additional sums).
* **Download & Verification**: Live monitoring of `.crdownload` completion, automatic renaming with sanitized legal docket conventions, and directory conflict resolution.
* **LLM Document Structuring**: Automatically extracts mortgagors, property parcel IDs, judgment amounts, and deceased status from raw PDFs.

### 2. SQLite Durable Deed Queue
Deed search and property extraction are decoupled from the main scraping thread via a custom **SQLite-backed task queue** (`database/deed_queue_db.py`):
* **Drop-in `queue.Queue` Interface**: Zero code friction (`put()`, `get()`, `task_done()`, `mark_failed()`).
* **WAL Mode Concurrency**: Uses Write-Ahead Logging for high-throughput, concurrent cross-thread/cross-process reads and writes.
* **Crash Resilience**: On startup, jobs stuck in `processing` state from interrupted or crashed runs are automatically recovered and reset to `pending`.
* **Bounded Retries**: Configurable `MAX_RETRIES` circuit-breaker that isolates failing jobs without blocking worker throughput.

### 3. Production Docker Environment
The platform runs headlessly inside Docker while bypassing anti-scraping defenses:
* **Xvfb (X Virtual Framebuffer)**: Runs Google Chrome with a full graphical display stack (`1920x1080x24`), allowing Undetected-Chromedriver to pass browser integrity checks that detect headless flags.
* **2GB Shared Memory (`shm_size: '2gb'`)**: Prevents Google Chrome renderer tabs from crashing during heavy PDF rendering.
* **Host Persistence**: All output PDFs, logs, Excel sheets, and queue databases are mounted via Docker volumes to ensure persistent local storage.

### 4. Comprehensive Automated Test Suite
The codebase is validated by **183 automated unit and integration tests** using `pytest`:
* **Zero Selenium Flakiness**: Tests focus strictly on data integrity, state machines, and file parsing.
* **Filesystem & DB Isolation**: Every queue and download test uses isolated `tmp_path` fixtures—zero leftover test files or database pollution.
* **Sub-5-Second Execution**: The entire test suite executes in ~3 seconds.

---

## County Coverage

| Jurisdiction | Coverage | Scraper Strategy |
|---|---|---|
| **New Jersey** | **All 21 Counties** (Atlantic, Bergen, Burlington, Camden, Cape May, Cumberland, Essex, Gloucester, Hudson, Hunterdon, Mercer, Middlesex, Monmouth, Morris, Ocean, Passaic, Salem, Somerset, Sussex, Union, Warren) | Centralized NJ Portal + SalesWeb Auction Pre-screening |
| **Florida** | **15 Key Counties** (Orange, Broward, Lee, Miami-Dade, Palm Beach, Duval, Osceola, Polk, Sarasota, Seminole, Volusia, Pasco, Clay, St. Johns, Manatee) | County-specific portal adapters with individual XPath mappings & download drivers |

---

## Quick Start & Installation

### Option 1: Docker (Recommended)

1. **Clone the repository and prepare configuration**:
   ```bash
   git clone https://github.com/your-username/Court-Scraper.git
   cd Court-Scraper
   cp .env.example .env   # Configure your Supabase, Groq, and API keys
   ```

2. **Launch with Docker Compose**:
   ```bash
   docker compose up --build -d
   ```

3. **Monitor Live Execution**:
   ```bash
   docker compose logs -f
   ```
   Open your browser to **`http://localhost:5511`** to access the real-time control dashboard.

---

### Option 2: Local Setup (Windows / Linux)

1. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Install the package in editable mode**:
   ```bash
   pip install -e .
   ```

4. **Launch the application**:
   ```bash
   python main.py
   ```

---

## Running the Test Suite

The platform includes a complete test suite verifying queue lifecycles, models, download cleaners, and pipeline transitions:

```bash
# Run all tests with short tracebacks
pytest tests/ -v

# Run a specific domain module
pytest tests/test_deed_queue.py -v
pytest tests/test_formatting.py -v
pytest tests/test_download_helpers.py -v
```

```
================= test session starts ==================
tests/test_deed_queue.py ............................    [ 15%]
tests/test_models.py ................................... [ 34%]
tests/test_core.py ..............................        [ 50%]
tests/test_formatting.py ............................... [ 81%]
tests/test_download_helpers.py ..............            [ 89%]
tests/test_report_generation.py ............             [ 96%]
tests/test_pipeline_base.py .......                      [100%]
================= 183 passed in 3.12s ==================
```

---

## Project Structure

```
Court-Scraper/
├── ai/                         # Unified LLM extraction (Groq, Anthropic, Gemini)
├── browser/                    # DriverPool, Undetected-Chromedriver, CAPTCHA solvers
├── config/                     # Pydantic v2 validated settings (.env + settings.json)
├── core/                       # CaseExecutor, SearchResult enums, CaseStatus contracts
├── counties/                   # County-specific navigation and scraper adapters (NJ + FL)
├── database/                   # Supabase service layer + SQLite durable deed queue
│   ├── deed_queue_db.py        # WAL-mode persistent queue for deed jobs
│   └── supabase_service.py     # PostgreSQL case & document sync
├── download/                   # File managers, download monitors, and keyword scanners
├── pipeline/                   # Modular pipeline engine
│   ├── base.py                 # PipelineBlock, BlockSignal, and Context dataclasses
│   ├── orchestrator.py         # Retry state machine and circuit breaker
│   └── blocks/                 # Pluggable execution blocks
├── tests/                      # 183+ automated pytest suite
│   ├── conftest.py             # Shared isolated fixtures (tmp_path SQLite DB)
│   ├── test_deed_queue.py      # Queue FIFO, concurrency, and crash-recovery tests
│   ├── test_models.py          # Case dataclass and county ID parsing tests
│   ├── test_formatting.py      # Filename & legal docket parsing tests
│   ├── test_download_helpers.py# Download completion and directory cleaner tests
│   ├── test_report_generation.py# Document classification & rule tests
│   └── test_pipeline_base.py   # State machine & context passing tests
├── Dockerfile                  # Production container with Google Chrome & Xvfb
├── docker-compose.yml          # Container configuration with 2GB shm & volume mounts
├── pyproject.toml              # Pytest configuration and build metadata
├── requirements.txt            # Python dependencies
├── app.py                      # Flask & SocketIO real-time control interface
└── main.py                     # Primary engine entrypoint
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
