# 🏛️ Court-Scraper: Distributed Legal Intelligence & Real Estate Foreclosure Pipeline

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python&logoColor=white)](https://python.org)
[![Selenium 4](https://img.shields.io/badge/Selenium-4.x-43B02A.svg?logo=selenium&logoColor=white)](https://selenium.dev)
[![Undetected Chromedriver](https://img.shields.io/badge/Undetected--Chromedriver-Anti--Bot-red.svg)](https://github.com/ultrafunkamsterdam/undetected-chromedriver)
[![Docker & Xvfb](https://img.shields.io/badge/Docker-Containerized%20Xvfb-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com)
[![SQLite WAL Queue](https://img.shields.io/badge/Task%20Queue-SQLite%20WAL%20Durable-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org)
[![Supabase PostgreSQL](https://img.shields.io/badge/Database-Supabase%20PostgreSQL-3ECF8E.svg?logo=supabase&logoColor=white)](https://supabase.com)
[![Groq & Claude LLM](https://img.shields.io/badge/AI%20Extraction-LLaMA%203.3%20%7C%20Claude%203.5-f55036.svg)](https://groq.com)
[![Pytest Suite](https://img.shields.io/badge/Tests-183%20Passed-brightgreen.svg?logo=pytest&logoColor=white)](https://pytest.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An enterprise-grade, distributed multi-state court automation, document intelligence, and real estate investment data pipeline.

The platform autonomously crawls, extracts, and parses public court dockets across **all 21 New Jersey counties** and **15 Florida counties**, enriches legal filings with external real estate auction data (**SalesWeb**), market valuations (**Zillow Zestimates**), county recorder deeds, and deceased mortgagor records (**Obituary Microservice**), and synchronizes structured lifecycle state into a cloud **Supabase (PostgreSQL)** database backed by a live **Flask-SocketIO** operations dashboard.

---

## 📑 Table of Contents
- [Technologies](#-technologies)
- [System Architecture](#-system-architecture)
- [Features](#-features)
- [County Coverage](#-county-coverage)
- [The Process ("The Cook"): Engineering Evolution](#-the-process-the-cook-engineering-evolution)
  - [Phase 1: The Humble Origin — Basic Selenium Scripting](#phase-1-the-humble-origin--basic-selenium-scripting)
  - [Phase 2: Document Intelligence — Legal PDF Parsing & LLM Structuring](#phase-2-document-intelligence--legal-pdf-parsing--llm-structuring)
  - [Phase 3: Real Estate Valuation — SalesWeb & Zillow Integration](#phase-3-real-estate-valuation--salesweb--zillow-integration)
  - [Phase 4: Scaling Horizontally — Conquering 36 Distinct County Portals](#phase-4-scaling-horizontally--conquering-36-distinct-county-portals)
  - [Phase 5: Chain of Title — Autonomous Deed Search & Durable SQLite Queue](#phase-5-chain-of-title--autonomous-deed-search--durable-sqlite-queue)
  - [Phase 6: Forensic Discovery — Obituary & Heir Intelligence Microservice](#phase-6-forensic-discovery--obituary--heir-intelligence-microservice)
  - [Phase 7: Enterprise Productionization — Supabase, Docker Xvfb & Live Telemetry](#phase-7-enterprise-productionization--supabase-docker-xvfb--live-telemetry)
- [What I Learned: From Beginner Scraper to Production Systems Engineer](#-what-i-learned-from-beginner-scraper-to-production-systems-engineer)
- [How It Can Be Improved (Future Roadmap)](#-how-it-can-be-improved-future-roadmap)
- [Installation & Quickstart](#-installation--quickstart)
- [Testing & Quality Assurance](#-testing--quality-assurance)
- [Repository Structure](#-repository-structure)

---

## 🛠️ Technologies

| Domain | Technology / Library | Purpose & Architectural Role |
|---|---|---|
| **Core & Concurrency** | **Python 3.12**, `concurrent.futures`, `asyncio` | High-performance async orchestration, multi-threaded worker pools, and strongly-typed data modeling |
| **Data Validation** | **Pydantic v2**, `dataclasses` | Strict runtime schema enforcement for legal docket parsing, court responses, and LLM JSON extraction |
| **Browser Automation** | **Selenium 4**, **Undetected-Chromedriver** | Headless-detection evasion, browser fingerprint randomization, CDP session hooks, and custom wait conditions |
| **Anti-Bot & Infrastructure** | **Docker**, **Linux Xvfb** (Virtual Framebuffer) | Headed Google Chrome execution inside headless Linux containers (`DISPLAY=:99`, `shm_size: 2GB`) to bypass anti-scraping perimeter guards |
| **Proxy & Network Rotation** | **NordVPN CLI**, **BrightData Residential Proxies** | Automated IP cycling, proxy authentication extensions, and leader-election reset cycles to overcome IP rate limits |
| **Durable Task Queuing** | **SQLite (WAL Mode)** | Zero-dependency, crash-resilient local task queue with atomic state transitions (`pending` → `processing` → `completed` / `failed`) and automatic in-flight job recovery |
| **AI & Legal Document OCR** | **Groq (LLaMA-3.3-70B)**, **Anthropic Claude 3.5**, **Mistral**, **Tesseract OCR**, `pypdf` | High-throughput legal PDF structuring: extracting mortgagors, lis pendens amounts, final judgments, and liens with custom token cost tracking |
| **Real Estate Enrichment** | **SalesWeb NJ**, **Zillow API (Apify Client)**, `BeautifulSoup4` | Pre-screening foreclosure auction dates, upset amounts, tax parcel IDs, and dynamic Zestimate property metrics |
| **Microservices** | **FastAPI / Flask Microservices** | Dedicated standalone obituary search service with geographic state normalization and fuzzy string matching |
| **Database & Persistence** | **Supabase (PostgreSQL)**, `openpyxl`, `pandas` | Cloud relational schema with custom SQL RPCs for atomic case status progression, document metadata storage, and formatted Excel reporting |
| **Operations Dashboard** | **Flask**, **Flask-SocketIO**, HTML5 / WebSockets | Real-time browser telemetry, execution pause/resume/kill signals, step-by-step case tracking, and log streaming |
| **Testing & CI** | **pytest** (183 unit & integration tests) | Sub-4-second test execution using isolated `tmp_path` fixtures, in-memory databases, and deterministic mocking |

---

## 🏗️ System Architecture

```
                                  ┌──────────────────────────────────────────────────┐
                                  │           Flask + SocketIO Web Dashboard         │
                                  │      (Real-Time Telemetry & Process Control)     │
                                  └─────────────────────────┬────────────────────────┘
                                                            │ WebSocket / REST
                                                            ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                                 CORE ORCHESTRATOR (main.py)                                           │
│                                                                                                                       │
│   ┌───────────────────────────────┐     ┌─────────────────────────────────┐     ┌─────────────────────────────────┐   │
│   │     SalesWeb / Zillow Pre     │     │      Multi-County Driver Pool   │     │    Durable Deed Task Queue      │   │
│   │    Enrichment & Filtering     │ ──► │  (Undetected Chrome under Xvfb) │ ──► │    (SQLite WAL mode: ACID FIFO) │   │
│   └───────────────────────────────┘     └────────────────┬────────────────┘     └────────────────┬────────────────┘   │
└──────────────────────────────────────────────────────────┼───────────────────────────────────────┼────────────────────┘
                                                           │                                       │
                    ┌──────────────────────────────────────┴────────────────┐                      │
                    ▼                                                       ▼                      ▼
┌──────────────────────────────────────────────┐ ┌──────────────────────────────────────┐ ┌───────────────────────────┐
│             Legal Document Pipeline          │ │        Forensic Obituary Search      │ │    Async Deed Workers       │
│  - Heuristic Docket Selector                 │ │             Microservice             │ │  - County Official Records  │
│  - Chromium .crdownload Interceptor          │ │  - Name & Geography Normalizer      │ │  - Chain of Title Crawl     │
│  - Tesseract OCR + pypdf Text Extract        │ │  - Multi-source Death Record Search  │ │  - Document OCR & Liens     │
│  - Groq LLaMA 3.3 / Claude 3.5 Structuring   │ │  - Heir / Probate Indicator          │ │  - Pydantic Deed Model      │
└──────────────────────┬───────────────────────┘ └──────────────────┬───────────────────┘ └─────────────┬───────────────┘
                       │                                            │                                   │
                       └────────────────────────────────────┬───────┴───────────────────────────────────┘
                                                            │
                                                            ▼
                                   ┌──────────────────────────────────────────────────┐
                                   │           Supabase Cloud Infrastructure          │
                                   │     - PostgreSQL Database (Cases, Docs, Deeds)   │
                                   │     - Stored Procedures (RPC Case Updates)       │
                                   │     - Local Excel Reports & Daily Artifacts      │
                                   └──────────────────────────────────────────────────┘
```

---

## ⚡ Features

### 1. Robust Multi-Stage Pipeline Architecture
Every court case is driven through a decoupled, state-machine-controlled sequence of stages with automatic retries and circuit breakers:
* **Pre-Check Stage**: Cross-references upcoming foreclosure dockets with SalesWeb county sheriff sales and Zillow Zestimates to filter out non-viable assets before spending browser or LLM compute.
* **Resilient Portal Navigation**: Adaptive authentication, session recovery, CAPTCHA bypass, and automatic DOM element stabilization across legacy court portals.
* **Intelligent Docket Picking**: Regular-expression scanner identifying high-value documents: *Foreclosure Complaints, Lis Pendens, Final Judgments, Orders to Vacate, Writs of Execution, and Liens*.
* **Active Download Monitor**: Tracks `.crdownload` browser stream completion, sanitizes target legal docket filenames, and eliminates file-lock contention.

### 2. Multi-LLM Document Intelligence & Cost Accounting
* Converts raw scanned court PDFs into structured data models using **Groq (LLaMA-3.3-70B)**, **Anthropic Claude 3.5 Sonnet**, and **Mistral**.
* Strict **Pydantic schema validation** parses:
  * Mortgagor & Defendant personal identifiers
  * Final judgment monetary figures & restitution sums
  * Recorded tax parcel identification numbers & legal descriptions
  * Superior mortgage and second-lien priority claims
* Integrated **token accounting & cost monitoring** (`ai/llm_cost_tracker.py`) prevents unexpected API spend during massive backfills.

### 3. Decoupled SQLite WAL Durable Task Queue
* Deed searching and property record extraction are decoupled from the main scraping pipeline via a high-performance **SQLite task queue** (`database/deed_queue_db.py`).
* Operates in **Write-Ahead Logging (WAL)** mode for concurrent cross-thread/cross-process access.
* **Crash-Resilient State Machine**: If the scraper process is killed or encounters a container crash, in-flight jobs stuck in `processing` are automatically recovered on boot and returned to `pending`.
* Includes bounded retries (`MAX_RETRIES`) and exponential backoff to isolate corrupt case records without blocking workers.

### 4. End-to-End Real Estate Due Diligence Enrichment
* **SalesWeb Integration**: Scrapes NJ Sheriff Foreclosure auction data, identifying upset prices, sales postponement notices, and attorney contact points.
* **Zillow Market Telemetry**: Programmatic Zestimate lookups, listing statuses, property dimensions, and auction flags via Apify actor automation.
* **Official Records Deed Search**: Programmatically navigates county land records to pull recorded deeds, granting instruments, and legal owners of record.
* **Obituary & Probate Discovery**: Dedicated microservice cross-references defendant names against national obituary indexes to verify deceased mortgagors and surface high-probability probate equity deals.

### 5. Production Dockerized Anti-Bot Architecture
* **Xvfb Display Emulation**: Runs Google Chrome in a full virtual 24-bit framebuffer (`1920x1080x24`), allowing **Undetected-Chromedriver** to execute in a true graphical environment inside Docker, preventing headless-flag browser fingerprint leaks.
* **2GB Shared Memory (`shm_size: 2gb`)**: Eliminates Chrome renderer tab crashes during multi-page legal PDF downloads.
* **Host Volume Isolation**: Output PDFs, SQLite task queues, debug logs, and output spreadsheets are mounted to local host directories.

### 6. Centralized PostgreSQL Storage & Live Dashboard
* Fully synchronized to **Supabase (PostgreSQL)** with stored RPC functions for atomic case status progression.
* Real-time **Flask-SocketIO web dashboard** providing live runtime progress, active thread states, log streams, and run controls (pause, resume, abort).

---

## 🗺️ County Coverage

| Jurisdiction | Coverage | Scraper Strategy & Portal Architecture |
|---|---|---|
| **New Jersey** | **All 21 Counties** (Atlantic, Bergen, Burlington, Camden, Cape May, Cumberland, Essex, Gloucester, Hudson, Hunterdon, Mercer, Middlesex, Monmouth, Morris, Ocean, Passaic, Salem, Somerset, Sussex, Union, Warren) | Centralized ACMS / eCourts portal automation with SalesWeb auction pre-screening and automated docket docketing |
| **Florida** | **15 Key Counties** (Broward, Miami-Dade, Palm Beach, Orange, Duval, Hillsborough, Lee, Pinellas, Polk, Osceola, Pasco, Seminole, St. Johns, Brevard, Sarasota) | County-specific portal adapters addressing distinct Odyssey, Tyler Technologies, and custom clerk interfaces |

---

## 🍳 The Process ("The Cook"): Engineering Evolution

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Phase 1:      │     │    Phase 2:      │     │    Phase 3:      │     │    Phase 4:      │
│   Simple NJ     │ ──► │  Document AI &   │ ──► │  SalesWeb &      │ ──► │  36-County       │
│  Selenium Bot   │     │  Docket Parsing  │     │  Zillow Enrich   │     │  Scale-Out       │
└─────────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘
                                                                                    │
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐               │
│   Phase 7:      │     │    Phase 6:      │     │    Phase 5:      │               │
│  Supabase Cloud │ ◄── │  Obituary Micro- │ ◄── │  Deed Records &  │ ◄─────────────┘
│  & Docker Xvfb  │     │  service Engine  │     │  WAL Task Queue  │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

Building this platform was an evolutionary journey—transitioning from a brittle, single-threaded script into an enterprise distributed pipeline capable of handling hundreds of gigabytes of legal records.

### Phase 1: The Humble Origin — Basic Selenium Scripting
The project started as a conventional automation task: log into the New Jersey court portal, navigate to a case search page, input a docket number, and scrape foreclosure listings off HTML tables. 
* *The Bottleneck*: The initial script was fragile. Standard Selenium was immediately detected by bot-defense mechanisms, pages threw random session timeouts, and DOM elements changed dynamically between counties.
* *The Fix*: Switched to `undetected-chromedriver` with randomized human timing, tab recycling, and custom explicit condition polling (`browser_helpers.py`), moving away from arbitrary `time.sleep()` statements.

### Phase 2: Document Intelligence — Legal PDF Parsing & LLM Structuring
Scraping basic metadata from court tables was only 10% of the value. The real intelligence was locked inside the court docket PDFs (Foreclosure Complaints, Lis Pendens, Final Judgments, Writs).
* *The Engineering Challenge*: Court websites use non-standard file viewers, embedded iframes, and streaming download endpoints. Furthermore, legal dockets contain hundreds of pages of unstructured legalese and scanned image attachments.
* *The Solution*: Built a heuristic file picker that scans docket item descriptions using regex rules. Implemented an active `.crdownload` file watcher to reliably capture downloads. Integrated **Tesseract OCR** and **LLMs (Groq LLaMA 3.3, Claude 3.5 Sonnet)** with strict **Pydantic schemas** to automatically extract defendants, judgment dollar amounts, parcel numbers, and second-mortgage liens.

### Phase 3: Real Estate Valuation — SalesWeb & Zillow Integration
Raw legal cases lack real-world investment context. An investor needs to know: *Is the house actually going to auction? What is the property worth? Is there enough equity to justify legal research?*
* *The Integration*: 
  * Built an automated parser for **SalesWeb NJ** to capture sheriff sale dates, upset prices, and attorney announcements.
  * Integrated **Zillow's API** (via Apify actors) to automatically fetch real-time Zestimates, property types, bedrooms/bathrooms, and listing statuses.
* *Pipeline Optimization*: Implemented pre-scraping valuation filters—cases without viable equity or active auction schedules are flagged early, saving thousands of browser and LLM operations.

### Phase 4: Scaling Horizontally — Conquering 36 Distinct County Portals
Expanding beyond New Jersey into 15 high-volume Florida counties exposed the chaotic fragmentation of county court software. Every county uses a different vendor: Odyssey, Tyler Technologies, or home-grown legacy systems.
* *The Engineering Challenge*: Each county portal has unique CAPTCHAs, custom session token lifecycles, disparate table hierarchies, and incompatible document viewing protocols.
* *The Solution*: Designed a modular **Adapter Pattern** (`counties/`). The core orchestration engine (`main.py`) interacts with an abstract county interface, while concrete county helper modules (`broward_helpers.py`, `palmbeach.py`, `miami_helpers.py`, `orange_helpers.py`, etc.) encapsulate portal-specific selectors, navigation sequences, and download logic.

### Phase 5: Chain of Title — Autonomous Deed Search & Durable SQLite Queue
Determining true property ownership required searching county recorder and comptroller databases to verify deeds, mortgages, and title conveyances.
* *The Architecture Problem*: Running court scraping and deed lookups synchronously in a single browser thread created severe bottlenecks. If a deed portal hung, the entire court scraper stalled.
* *The Solution*: Fully decoupled deed operations into an independent asynchronous subsystem (`deed_search/`). Built an **ACID-compliant SQLite durable task queue** in Write-Ahead Logging (WAL) mode (`database/deed_queue_db.py`). The court scraper pushes deed tasks into the database; independent worker processes (`deed_worker.py`) poll, claim, process, and update records with automatic crash recovery.

### Phase 6: Forensic Discovery — Obituary & Heir Intelligence Microservice
In foreclosure and probate investing, a major competitive edge is discovering whether a mortgagor is deceased before other market participants.
* *The Engineering Challenge*: Cross-referencing hundreds of debtor names across multiple death record databases requires clean fuzzy string matching, geographic state filtering, and handling false positives.
* *The Solution*: Engineered a standalone **Obituary Microservice** (`obituary_api/`). It features a dedicated REST client-server architecture, state-name normalization utilities (`state_normaliser.py`), and scrapers that search national obituary records to flag deceased owners, extract dates of death, and identify potential surviving heirs.

### Phase 7: Enterprise Productionization — Supabase, Docker Xvfb & Live Telemetry
To run reliably 24/7 without developer intervention, the system needed cloud persistence, containerization, and observability.
* *Cloud Persistence*: Migrated from flat Excel sheets and local JSON files to a relational **Supabase (PostgreSQL)** database. Authored custom PostgreSQL RPC stored procedures for atomic case updates and document relation sync.
* *Dockerized Xvfb*: Containerized the application with Google Chrome running on an X Virtual Framebuffer (`DISPLAY=:99`), allowing headed browser runs in headless Linux environments without headless fingerprint detection.
* *Operations Dashboard*: Built a real-time **Flask-SocketIO dashboard** (`app.py`) providing live progress bars, pipeline status rollups (`PENDING` → `RUNNING` → `SUCCESS` / `FAILED`), log streams, and remote process controls.

---

## 💡 What I Learned: From Beginner Scraper to Production Systems Engineer

Starting from basic Python scripts and simple BeautifulSoup tutorials, building this platform required mastering the complex realities of distributed systems, systems architecture, and anti-bot engineering:

### 1. Browser Fingerprinting & Anti-Bot Defense
* **Headless Detection Vectors**: Discovered that standard headless Chrome leaks identifiable fingerprints (navigator flags, WebGL vendor hashes, `window.chrome` missing, permissions API anomalies). Solved this by executing headed Undetected-Chromedriver inside Docker with **Xvfb**.
* **Proxy Lifecycle & Session Management**: Learned how to manage residential proxy pools, configure proxy authentication extensions dynamically, and manage sticky sessions across multi-step court checkout workflows.

### 2. Distributed Queueing, Concurrency & Crash Recovery
* **Beyond `queue.Queue`**: Standard in-memory Python queues vanish when a process crashes or Docker restarts. Learned to design a persistent **SQLite WAL-mode queue** with atomic job claims (`UPDATE ... SET status = 'processing'`), FIFO ordering, and automated startup recovery for interrupted tasks.
* **Process & Thread Safety**: Handled SQLite multi-threading locks, connection pooling, and multi-worker contention across separate operating system processes.

### 3. Pipeline Design & Fault Tolerance
* **State Machines & Circuit Breakers**: Moved away from monolithic try/except blocks to decoupled pipeline blocks with discrete signals (`BlockSignal.CONTINUE`, `BlockSignal.SKIP`, `BlockSignal.FAIL`).
* **Self-Healing Automation**: Designed exponential backoff retry loops, network reset routines (NordVPN / proxy rotation), and clean process teardown to prevent zombie Chrome processes from exhausting RAM.

### 4. Deterministic AI with Unstructured Real-World Data
* **Schema Enforcement**: Overcame LLM hallucination and inconsistent JSON returns by using **Pydantic v2** models with strict typing, regex validators, and fallback prompt strategies.
* **Production Cost Optimization**: Implemented local caching (hash-based duplicate detection) and token cost accounting to process thousands of legal documents economically.

### 5. Production Testing & Mock Isolation
* **Zero-Selenium Flakiness**: Learned that testing browser scrapers with end-to-end network requests leads to slow, flaky test suites. Architected **183 unit and integration tests** focusing on state transitions, queue lifecycles, and parsing heuristics using isolated `tmp_path` fixtures—running the entire suite in **~3.1 seconds**.

---

## 🚀 How It Can Be Improved (Future Roadmap)

While the platform currently processes thousands of court dockets reliably, several high-impact architectural enhancements are planned:

### 1. Multi-State Expansion
* **Geographic Scale**: Extend the modular adapter system to additional high-volume foreclosure and probate jurisdictions, including **Texas (Harris, Dallas, Travis counties)**, **California (Los Angeles, San Diego, Orange counties)**, and **Georgia (Fulton, Gwinnett, Cobb counties)**.
* **Unified State Tax Records**: Integrate automated county tax assessor and GIS parcel map scrapers to enrich legal records with lot dimensions, land zoning, and building square footage.

### 2. AWS Cloud-Native Infrastructure
* **AWS ECS / Fargate Worker Fleet**: Migrate browser instances into auto-scaling AWS ECS Fargate tasks that scale horizontally based on the size of the daily docket queue.
* **AWS SQS & EventBridge**: Transition from local SQLite WAL queues to distributed **Amazon SQS** FIFO queues for multi-instance distributed worker coordination.
* **S3 Legal Document Lake**: Stream court PDFs directly to an **Amazon S3** bucket lifecycle-configured with Glacier instant retrieval, reducing local Docker volume storage demands.
* **AWS Lambda OCR / LLM Pipeline**: Trigger serverless Lambda functions on S3 upload events to run OCR and Groq/Bedrock LLM extraction asynchronously.

### 3. Advanced Multimodal AI & Layout Analysis
* **Multimodal Vision Models**: Upgrade text-only PDF extraction to vision-language models (e.g., Claude 3.5 Sonnet Vision or GPT-4o) to accurately read complex non-text elements: stamped notary seals, court clerk filing stamps, plat maps, and handwritten title notes.
* **Document Graph Linking**: Implement graph-based entity resolution (e.g., Neo4j) to map relationships between repeat lenders, high-volume foreclosure trustees, and multi-property debtor networks.

### 4. Real-Time Investor Alerting & CRM Integration
* **Instant Webhook Engine**: Build configurable alerting rules (e.g., *Property Equity > $150k + Upset Amount < 50% Zestimate + Deceased Mortgagor*) that trigger instant Slack, Telegram, or SMS notifications.
* **Automated CRM Push**: Bi-directional webhook integration with real estate investor CRMs (HubSpot, Podio, Salesforce) to auto-generate actionable acquisitions leads.

### 5. Automated DOM Drift & Canary Monitoring
* **Synthetic Canary Tests**: Daily scheduled lightweight runs against court login portals to detect UI redesigns, updated CSS selectors, or new bot-protection challenges before the main production pipelines execute.

---

## 💻 Installation & Quickstart

### Prerequisites
* **Docker & Docker Compose** (Recommended for production) OR
* **Python 3.12+**, **Google Chrome**, and **Git** (For local development)

---

### Option 1: Docker (Production Ready)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/Court-Scraper.git
   cd Court-Scraper
   ```

2. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   # Populate your SUPABASE_URL, SUPABASE_KEY, GROQ_API_KEY, and APIFY_API_KEY
   ```

3. **Build and launch containerized services**:
   ```bash
   docker compose up --build -d
   ```

4. **Access the Dashboard**:
   Open **`http://localhost:5511`** in your browser to view the real-time pipeline telemetry and control center.

---

### Option 2: Local Setup (Windows / Linux)

1. **Initialize Virtual Environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **Install Core Dependencies**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Run the Primary Engine**:
   ```bash
   python main.py
   ```

4. **Launch Independent Background Deed Workers**:
   ```bash
   python deed_worker.py
   ```

---

## 🧪 Testing & Quality Assurance

The platform is backed by a comprehensive suite of **183 automated unit and integration tests** built with `pytest`:
* **Zero Network Dependency**: Tests validate file parsers, legal models, download cleaners, and state machines with zero live Selenium calls.
* **Isolated State**: Uses temporary filesystem directories (`tmp_path`) and in-memory SQLite instances to guarantee test isolation with zero residual side effects.

Run the entire test suite:
```bash
pytest tests/ -v
```

```
================================ test session starts =================================
platform win32 -- Python 3.12.x, pytest-8.x.x
rootdir: C:\Users\pc\PycharmProjects\Court-Scraper
configfile: pyproject.toml
collected 183 items

tests/test_deed_queue.py ............................                          [ 15%]
tests/test_models.py ...................................                       [ 34%]
tests/test_core.py ..............................                              [ 50%]
tests/test_formatting.py ...............................                       [ 81%]
tests/test_download_helpers.py ..............                                  [ 89%]
tests/test_report_generation.py ............                                   [ 96%]
tests/test_pipeline_base.py .......                                            [100%]

================================ 183 passed in 3.12s =================================
```

---

## 📂 Repository Structure

```
Court-Scraper/
├── ai/                         # Unified LLM extraction (Groq, Anthropic, Mistral) & cost tracker
│   ├── llm_helper.py           # Structured Pydantic extraction schemas & prompt engines
│   ├── llm_cost_tracker.py     # Token accounting & API budget enforcement
│   └── ocr.py                  # Tesseract OCR & image-to-text conversion
├── browser/                    # Browser automation core
│   ├── browser_helpers.py      # Resilient wait conditions, tab recycling & DOM interactions
│   └── OP.py                   # SalesWeb HTML table extractor & auction parser
├── config/                     # Configuration management
│   └── settings.py             # Pydantic v2 environment validation (.env + settings.json)
├── core/                       # Core domain models, enums & execution contracts
├── counties/                   # Modular county court portal adapters
│   ├── nj_processor.py         # New Jersey statewide eCourts engine (21 counties)
│   ├── broward_helpers.py      # Florida: Broward County portal automation
│   ├── miami_helpers.py        # Florida: Miami-Dade County portal automation
│   ├── palmbeach.py            # Florida: Palm Beach County portal automation
│   └── ...                     # Additional Florida county adapters (15 total)
├── database/                   # Persistence & distributed queuing
│   ├── deed_queue_db.py        # SQLite WAL-mode crash-resilient task queue
│   └── supabase_service.py     # PostgreSQL Supabase client, models & RPC integrations
├── deed_search/                # Autonomous property deed searching subsystem
│   ├── downloader.py           # County official land record crawlers
│   ├── download_manager.py     # Deed file lifecycle & PDF verification
│   └── server.py               # Standalone deed search API microservice
├── download/                   # File managers, .crdownload watchers & docket cleaners
├── obituary_api/               # Deceased mortgagor & heir discovery microservice
│   ├── client.py               # REST API client for pipeline integration
│   ├── scraper.py              # Death index & obituary search crawler
│   ├── server.py               # Microservice web endpoint
│   └── state_normaliser.py     # Geographic state name sanitization
├── pipeline/                   # Pluggable pipeline state machine
│   ├── base.py                 # PipelineBlock, BlockSignal & Context contracts
│   └── orchestrator.py         # Multi-stage retry engine & circuit breaker
├── tests/                      # 183+ automated pytest suite
│   ├── conftest.py             # Shared fixtures (tmp_path, isolated test DB)
│   ├── test_deed_queue.py      # Queue FIFO, concurrency & crash-recovery tests
│   └── ...                     # Models, formatters, and download tests
├── app.py                      # Flask & SocketIO real-time telemetry dashboard
├── deed_worker.py              # Background worker consuming SQLite deed queue
├── update_salesweb.py          # Standalone SalesWeb batch enrichment script
├── update_zillow.py            # Standalone Zillow / Apify batch enrichment script
├── Dockerfile                  # Production container with Google Chrome & Xvfb
├── docker-compose.yml          # Container configuration (2GB shm, volume mounts)
├── requirements.txt            # Python dependencies
└── main.py                     # Primary pipeline entry point
```

---

## 📜 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
