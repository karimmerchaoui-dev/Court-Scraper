# 🏛️ Court-Scraper: Automated Real Estate & Court Case Intelligence Pipeline

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg?logo=python&logoColor=white)](https://python.org)
[![Selenium 4](https://img.shields.io/badge/Selenium-4.x-43B02A.svg?logo=selenium&logoColor=white)](https://selenium.dev)
[![Undetected Chromedriver](https://img.shields.io/badge/Undetected--Chromedriver-Anti--Bot-red.svg)](https://github.com/ultrafunkamsterdam/undetected-chromedriver)
[![Docker & Xvfb](https://img.shields.io/badge/Docker-Containerized%20Xvfb-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com)
[![SQLite WAL Queue](https://img.shields.io/badge/Task%20Queue-SQLite%20WAL%20Durable-003B57.svg?logo=sqlite&logoColor=white)](https://www.sqlite.org)
[![Supabase PostgreSQL](https://img.shields.io/badge/Database-Supabase%20PostgreSQL-3ECF8E.svg?logo=supabase&logoColor=white)](https://supabase.com)
[![Groq & Claude LLM](https://img.shields.io/badge/AI%20Extraction-LLaMA%203.3%20%7C%20Claude%203.5-f55036.svg)](https://groq.com)
[![Pytest Suite](https://img.shields.io/badge/Tests-183%20Passed-brightgreen.svg?logo=pytest&logoColor=white)](https://pytest.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

If you've ever tried to analyze distressed real estate deals, you know how painful the research is. Court dockets are stuck in legacy government websites, deeds are buried in county clerk databases, auction dates live on third-party sheriff sites, and property values are on Zillow. To make matters worse, the most valuable details are trapped inside messy scanned PDFs that you have to download and read by hand.

**Court-Scraper solves this problem.** It is an automated data pipeline that connects all these dots. It collects court cases across **all 21 New Jersey counties** and **15 Florida counties**, pulls the legal filings and deeds, extracts mortgage debt and unpaid liens from SalesWeb, checks Zillow for property values, searches obituaries to find deceased owners and their heirs, and organizes everything into a centralized database.

---

## 📑 Table of Contents
- [What The Pipeline Extracts (The Complete Picture)](#-what-the-pipeline-extracts-the-complete-picture)
- [System Architecture](#-system-architecture)
- [Technologies](#-technologies)
- [Key Features](#-key-features)
- [County Coverage](#-county-coverage)
- [The Process ("The Cook"): How The Project Evolved](#-the-process-the-cook-how-the-project-evolved)
  - [Step 1: Starting with a Basic New Jersey Scraper](#step-1-starting-with-a-basic-new-jersey-scraper)
  - [Step 2: Pulling and Analyzing Real Court Documents](#step-2-pulling-and-analyzing-real-court-documents)
  - [Step 3: Bringing in SalesWeb and Zillow](#step-3-bringing-in-salesweb-and-zillow)
  - [Step 4: Expanding to 15 Florida Counties](#step-4-expanding-to-15-florida-counties)
  - [Step 5: Adding Deed Searches Without Slowing Down the Pipeline](#step-5-adding-deed-searches-without-slowing-down-the-pipeline)
  - [Step 6: Finding Deceased Property Owners & Reading Obituaries](#step-6-finding-deceased-property-owners--reading-obituaries)
  - [Step 7: Bringing It All Together in Supabase with Docker & a Live UI](#step-7-bringing-it-all-together-in-supabase-with-docker--a-live-ui)
- [What I Learned: Leveling Up as a Developer](#-what-i-learned-leveling-up-as-a-developer)
- [How It Can Be Improved (Next Steps)](#-how-it-can-be-improved-next-steps)
- [Quickstart & Setup](#-quickstart--setup)
- [Testing](#-testing)
- [Project Layout](#-project-layout)

---

## 🎯 What The Pipeline Extracts (The Complete Picture)

Most web scrapers just grab table rows from a webpage. This system does deep research on every single property, pulling information from multiple independent sources and storing it cleanly in one place:

```
                               ┌────────────────────────────────────────────────────────┐
                               │           EVERYTHING EXTRACTED FOR EACH CASE           │
                               └───────────────────────────┬────────────────────────────┘
                                                           │
        ┌───────────────────┬──────────────────────┼──────────────────────┬───────────────────┐
        ▼                   ▼                      ▼                      ▼                   ▼
┌───────────────┐   ┌───────────────┐      ┌───────────────┐      ┌───────────────┐   ┌───────────────┐
│ Court Records │   │ Deed Records  │      │ Debt & Liens  │      │ Property Info │   │ Obituary &    │
│  & Legal PDFs │   │ County Clerks │      │   SalesWeb    │      │    Zillow     │   │     Heirs     │
└───────┬───────┘   └───────┬───────┘      └───────┬───────┘      └───────┬───────┘   └───────┬───────┘
        │                   │                      │                      │                   │
        ▼                   ▼                      ▼                      ▼                   ▼
 • Case number       • Warranty deeds       • Original mortgage    • Zestimate price   • Death confirmation
 • Filing date       • Quitclaim deeds      • Unpaid balance       • Estimated equity  • Date of death
 • Lis pendens       • Book & page number   • Second mortgages     • Beds & baths      • Age & city
 • Final judgment    • Instrument ID        • Tax liens            • Square footage    • Full obit text
 • Writs & orders    • Full owner history   • Sheriff upset bid    • Listing status    • Surviving family
        │                   │                      │                      │                   │
        └───────────────────┴──────────────────────┼──────────────────────┴───────────────────┘
                                                   │
                                                   ▼
                         ┌─────────────────────────────────────────────────────┐
                         │      ORGANIZED IN SUPABASE (POSTGRESQL) DATABASE    │
                         │   All data linked together by property and case ID  │
                         │   Ready to search, filter, or export to Excel       │
                         └─────────────────────────────────────────────────────┘
```

| Category | What Gets Extracted | Where It Comes From | Why It Matters |
|---|---|---|---|
| **🏛️ Official Court Documents** | Case number, filing date, complaints, lis pendens notices, final judgment amounts, judge orders, and writs of execution | County court clerk portals via Selenium & OCR | Shows the exact legal stage of the case and how close it is to being sold at auction |
| **📜 Property Deeds** | Recorded deeds, grantor & grantee names, instrument numbers, book/page, parcel IDs, and lot/block info | County recorder databases (`deed_search/`) | Verifies who actually owns the home on paper and uncovers unrecorded title transfers |
| **💰 Loans, Liens & Debt** | Original mortgage amounts, unpaid principal balance, back interest, second mortgages, tax liens, HOA claims, and sheriff auction upset prices | Court judgments + **SalesWeb** (`browser/OP.py`) | Tells you the total debt on the property so you know if there is enough equity to make a deal |
| **👤 Homeowner Information** | Borrower names, spouses, co-defendants, bank attorneys, and service addresses | Court dockets & structured AI extraction | Gives you the exact names of the owners and their lawyers so you know who to contact |
| **🏡 Property Value & Details** | Zestimates, equity margin, home type (single-family, condo, etc.), bedrooms, bathrooms, and square feet | **Zillow API** via Apify (`update_zillow.py`) | Gives an instant market estimate without having to look up every address manually |
| **🕊️ Deceased Owners & Obituaries** | Whether the owner passed away, date of death, city of passing, full obituary text, and names of surviving heirs/children | Standalone **Obituary Service** (`obituary_api/`) | Identifies probate situations where surviving family members may want to sell the house quickly |
| **🗄️ Central Database** | Normalized database tables linking cases, owners, deeds, liens, and obituaries together, with instant Excel exports | **Supabase (PostgreSQL)** + `openpyxl` / `pandas` | Keeps all findings organized in one central place instead of scattered across folders and spreadsheets |

---

## 🏗️ System Architecture

Here is how the data flows through the application:

```
                                  ┌──────────────────────────────────────────────────┐
                                  │             Flask Web Dashboard & UI             │
                                  │    Real-time progress, log streaming & controls  │
                                  └─────────────────────────┬────────────────────────┘
                                                            │ WebSockets / HTTP
                                                            ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                             MAIN CONTROLLER (main.py)                                                 │
│                                                                                                                       │
│   ┌───────────────────────────────┐     ┌─────────────────────────────────┐     ┌─────────────────────────────────┐   │
│   │   Pre-Screening Step          │     │    Browser Automation Pool      │     │      Durable Task Queue         │   │
│   │   (SalesWeb & Zillow checks   │ ──► │ (Undetected Chrome running      │ ──► │ (SQLite WAL database:           │   │
│   │    before heavy scraping)     │     │  inside virtual Xvfb screen)    │     │  saves jobs so nothing is lost) │   │
│   └───────────────────────────────┘     └────────────────┬────────────────┘     └────────────────┬────────────────┘   │
└──────────────────────────────────────────────────────────┼───────────────────────────────────────┼────────────────────┘
                                                           │                                       │
                    ┌──────────────────────────────────────┴────────────────┐                      │
                    ▼                                                       ▼                      ▼
┌──────────────────────────────────────────────┐ ┌──────────────────────────────────────┐ ┌───────────────────────────┐
│          Court Document Processing           │ │         Obituary Search Service      │ │      Deed Search Workers    │
│  - Finds key PDFs (complaints, judgments)    │ │  - Cleans names and states           │ │  - Searches county records  │
│  - Waits for browser download to finish      │ │  - Searches public death records     │ │  - Downloads recorded deeds │
│  - Runs OCR on scanned images                │ │  - Reads obit text for family members│ │  - Parses instrument IDs    │
│  - Uses LLMs (Groq / Claude) to pull amounts │ │  - Flags probate opportunities       │ │  - Updates queue when done  │
└──────────────────────┬───────────────────────┘ └──────────────────┬───────────────────┘ └─────────────┬───────────────┘
                       │                                            │                                   │
                       └────────────────────────────────────┬───────┴───────────────────────────────────┘
                                                            │
                                                            ▼
                                   ┌──────────────────────────────────────────────────┐
                                   │            Supabase Cloud Database               │
                                   │    PostgreSQL database with all cases, files,    │
                                   │    owners, debts, and automatic status updates   │
                                   └──────────────────────────────────────────────────┘
```

---

## 🛠️ Technologies

| Part of the System | Tool / Library | Why It's Used |
|---|---|---|
| **Language & Core** | **Python 3.12** | Core language for the whole project, using async and thread pools for concurrent jobs |
| **Data Models** | **Pydantic v2** | Makes sure data coming from web pages and LLMs matches strict schemas before entering the database |
| **Web Automation** | **Selenium 4**, **Undetected-Chromedriver** | Controls the browser and bypasses Cloudflare and bot detection on county websites |
| **Container & Display** | **Docker**, **Linux Xvfb** | Runs Chrome with a real virtual screen (`DISPLAY=:99`) inside Docker so websites don't know it's headless |
| **Proxies & IP Rotation** | **NordVPN CLI**, **BrightData Proxies** | Automatically rotates IP addresses when county servers start rate-limiting requests |
| **Persistent Task Queue** | **SQLite (WAL Mode)** | A lightweight, file-based task queue that doesn't lose jobs even if the program crashes or gets restarted |
| **AI & Document Parsing** | **Groq (LLaMA 3.3)**, **Claude 3.5**, **Tesseract OCR** | Reads messy court PDFs and pulls out judgment amounts, loan balances, and names into clean JSON |
| **Real Estate Data** | **SalesWeb**, **Zillow API (Apify)** | Pulls upcoming sheriff auction dates, upset debt amounts, and estimated property values |
| **Microservices** | **FastAPI / Flask** | A separate helper service dedicated to searching obituaries and standardizing state names |
| **Database** | **Supabase (PostgreSQL)** | Central database storing every case, deed, document, and debt figure, with custom stored procedures |
| **Web Dashboard** | **Flask**, **Socket.IO** | Simple browser UI to watch jobs run live, see logs, and pause or stop workers |
| **Testing** | **pytest** (183 tests) | Fast unit tests running in ~3 seconds using isolated temporary folders instead of hitting live websites |

---

## ⚡ Key Features

- **Decoupled Multi-Step Pipeline**: Every case runs through clean, separate stages: pre-screening, logging in, finding documents, downloading files, reading text with AI, and updating the database. If one step has an issue, it retries cleanly without crashing the whole run.
- **Intelligent Document Finder**: Instead of downloading every single court paper, the script scans docket titles using smart regex patterns to pick only the high-value files: *Foreclosure Complaints, Lis Pendens, Final Judgments, and Orders to Vacate*.
- **AI Document Extraction with Cost Controls**: Scanned PDFs are read with OCR and structured using **Groq** and **Claude**. An integrated cost tracker (`ai/llm_cost_tracker.py`) monitors token usage so API costs stay predictable.
- **Durable Background Queue**: Deed searches run independently from court scraping. They sit in a local **SQLite WAL queue** (`database/deed_queue_db.py`). If a worker crashes halfway through, it recovers on startup and re-queues any interrupted tasks.
- **Real Estate & Debt Verification**: Automatically combines sheriff auction data from SalesWeb with Zillow Zestimates and mortgage numbers from court dockets. You immediately see the property value vs. total unpaid debt.
- **Obituary & Heir Detection**: Checks property owners against national obituary records. If an owner passed away, the script reads the obituary text to pull out surviving family members and flags it as a probate lead.
- **Production-Ready Docker Setup**: Chrome runs inside a virtual Xvfb screen with 2GB of shared memory (`shm_size: 2gb`). This prevents memory crashes during PDF downloads and passes bot checks.
- **Live Monitoring Dashboard**: A clean web interface (`http://localhost:5511`) lets you watch cases move from `PENDING` to `RUNNING` to `SUCCESS` in real time with live logs.

---

## 🗺️ County Coverage

| State | Counties Supported | How It Works |
|---|---|---|
| **New Jersey** | **All 21 Counties** (Atlantic, Bergen, Burlington, Camden, Cape May, Cumberland, Essex, Gloucester, Hudson, Hunterdon, Mercer, Middlesex, Monmouth, Morris, Ocean, Passaic, Salem, Somerset, Sussex, Union, Warren) | Automated through the centralized NJ eCourts system, combined with SalesWeb sheriff auction data |
| **Florida** | **15 Major Counties** (Broward, Miami-Dade, Palm Beach, Orange, Duval, Hillsborough, Lee, Pinellas, Polk, Osceola, Pasco, Seminole, St. Johns, Brevard, Sarasota) | Custom browser adapters built for each county's specific portal layout and search interface |

---

## 🍳 The Process ("The Cook"): How The Project Evolved

Building this system wasn't done overnight. It grew step-by-step from a simple script into a full data pipeline as I discovered real problems and engineered solutions for them.

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│     Step 1:      │     │     Step 2:      │     │     Step 3:      │     │     Step 4:      │
│  Basic Selenium  │ ──► │  Court Document  │ ──► │    SalesWeb &    │ ──► │    15 Florida    │
│    NJ Scraper    │     │   AI Analysis    │     │  Zillow Enrich   │     │     Counties     │
└──────────────────┘     └──────────────────┘     └──────────────────┘     └──────────────────┘
                                                                                    │
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐               │
│     Step 7:      │     │     Step 6:      │     │     Step 5:      │               │
│  Supabase Cloud  │ ◄── │  Obituary Search │ ◄── │  Deed Searching  │ ◄─────────────┘
│  & Live Dashboard│     │   & Heir Finder  │     │   & Task Queue   │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

### Step 1: Starting with a Basic New Jersey Scraper
I started with a simple goal: write a Python script using Selenium to log into the New Jersey court website and scrape foreclosure case tables.
* *The Problem*: The website was tricky. Standard Selenium got blocked immediately, tables took time to load, sessions timed out randomly, and hardcoded `time.sleep()` calls made the script slow and fragile.
* *The Fix*: I moved to `undetected-chromedriver` to look like a real browser, added random delays, recycled browser tabs, and wrote explicit wait helpers (`browser/browser_helpers.py`) that wait for real page elements instead of guessing wait times.

### Step 2: Pulling and Analyzing Real Court Documents
Scraping case tables only gave me names and dates. The real gold was hidden inside the court PDFs—like the Foreclosure Complaint and the Final Judgment.
* *The Problem*: A single court case can have dozens of docket entries. Downloading all of them wasted time and disk space. Even after downloading, the documents were messy legal texts or scanned images.
* *The Fix*: I wrote a regex scanner that searches docket titles and only downloads key files (*Complaints, Lis Pendens, Final Judgments*). I built an active download watcher to track `.crdownload` files, ran OCR on scanned pages, and plugged in **Groq (LLaMA 3.3)** and **Claude** with strict **Pydantic** models to extract exact numbers: loan amounts, unpaid balances, and parcel IDs.

### Step 3: Bringing in SalesWeb and Zillow
Once I had court numbers, I needed real-world real estate context: *Is this house actually going to auction? What is it worth?*
* *The Solution*: 
  * I built an automated scraper for **SalesWeb NJ** to pull sheriff auction dates, upset prices, and plaintiff bank information.
  * I connected the **Zillow API** (via Apify) to automatically pull property Zestimates, bedrooms, bathrooms, and square footage.
* *The Win*: By checking SalesWeb and Zillow first, the pipeline can skip properties that don't have enough equity, saving hours of unnecessary browser work.

### Step 4: Expanding to 15 Florida Counties
New Jersey has a centralized court portal, but Florida is completely fragmented. Every single county in Florida uses a different software vendor with its own layout.
* *The Problem*: Broward County looks nothing like Miami-Dade, which looks nothing like Palm Beach. Writing one giant script for all of them was impossible.
* *The Fix*: I used an **Adapter Pattern** (`counties/`). The main runner (`main.py`) talks to a standard county interface, and each county has its own clean helper file (`broward_helpers.py`, `palmbeach.py`, `miami_helpers.py`, etc.) that handles that county's specific forms, search buttons, and table formats.

### Step 5: Adding Deed Searches Without Slowing Down the Pipeline
To confirm who actually owned each house, I needed to search county recorder databases for recorded deeds.
* *The Problem*: Searching deed portals in the same browser thread created a major bottleneck. If a county deed site lagged or hung, the entire court scraper stopped in its tracks.
* *The Fix*: I separated deed searching into its own independent background process (`deed_search/`). I built a persistent **SQLite task queue** in WAL mode (`database/deed_queue_db.py`). The main scraper simply drops deed jobs into the queue, and background workers (`deed_worker.py`) pick them up and process them independently. If a worker is interrupted, it automatically resets on reboot so no job is lost.

### Step 6: Finding Deceased Property Owners & Reading Obituaries
In real estate, discovering that an owner has passed away is huge. The house often goes into probate, and the heirs may want to sell before the foreclosure auction happens.
* *The Solution*: I built a dedicated **Obituary Microservice** (`obituary_api/`). The scraper takes the debtor's name, cleans up the state name (`state_normaliser.py`), and searches public death registries. When it finds a match, it pulls the **date of death, city, and full obituary text**, and parses out the names of surviving family members (children, spouse, siblings) to find motivated heirs.

### Step 7: Bringing It All Together in Supabase with Docker & a Live UI
With five different data streams running (court dockets, deeds, SalesWeb, Zillow, and obituaries), keeping data in local spreadsheets and JSON files was no longer manageable.
* *The Database*: I connected everything to **Supabase (PostgreSQL)**. I created relational tables that link cases, deeds, documents, liens, and obituaries using foreign keys, and wrote custom PostgreSQL stored procedures (RPCs) to update case statuses safely.
* *Docker & Xvfb*: I packaged the app into a Docker container running Google Chrome inside a virtual display buffer (`Xvfb`), giving Chrome 2GB of shared RAM so it can render heavy PDFs without crashing.
* *Live UI*: I built a web dashboard with Flask and WebSockets (`app.py`) so anyone on the team can watch the scraper work live, pause tasks, and download updated Excel reports.

---

## 💡 What I Learned: Leveling Up as a Developer

When I started this project, I only had basic Python knowledge and had built simple scrapers using `requests` and `time.sleep()`. Building this real-world system taught me practical software engineering lessons that tutorials never cover:

### 1. Real-World Anti-Bot Evasion
* **Why headless Chrome gets banned**: Running Chrome with `--headless` leaves clear fingerprints (like missing plugins and modified navigator variables) that modern sites detect instantly. I learned how to use `Xvfb` (virtual displays) inside Docker so Chrome runs in headed mode without needing an actual physical monitor.
* **Smart waiting over `time.sleep()`**: Hardcoded sleep timers make scripts either painfully slow or completely broken. Learning to wait for specific DOM conditions and state changes made the scrapers twice as fast and much more reliable.

### 2. Building Resilient Task Queues
* **Why memory queues aren't enough**: Python's built-in `queue.Queue` vanishes if the script crashes or your computer restarts.
* **Learning SQLite WAL Mode**: I learned how SQLite's Write-Ahead Logging (WAL) allows multiple threads and processes to read and write safely at the same time, and how to build a durable queue that survives sudden crashes.

### 3. Making AI Useful for Real Data
* **Avoiding hallucinations**: Raw LLM prompts often return random or unstructured text. I learned how to combine **Pydantic schemas** with strict JSON prompt validation to ensure that dollar amounts, names, and case numbers always come back in predictable formats.
* **Tracking token spend**: Running thousands of PDF pages through LLMs gets expensive quickly. I built an automatic token cost counter to keep API expenses visible and predictable.

### 4. Writing Tests That Don't Flake
* **Testing without live browsers**: In the beginning, my tests were slow and flaky because they hit real websites.
* **Testing business logic**: I restructured tests using `pytest` fixtures and temporary directories (`tmp_path`). The test suite validates file renaming, models, queue transitions, and text parsers in **~3 seconds** without touching live court servers.

---

## 🚀 How It Can Be Improved (Next Steps)

Here are the most practical improvements planned for the project:

- **Add More High-Volume States**: Build adapters for high-growth states with active foreclosure markets, starting with **Texas (Harris, Dallas, Travis counties)** and **California (Los Angeles, San Diego, Orange counties)**.
- **Move Workers to AWS**: Move the browser workers into **AWS ECS Fargate** tasks that spin up only when there are new cases, store PDFs directly in **Amazon S3**, and use **Amazon SQS** for task queues.
- **Multimodal AI for Scanned Documents**: Upgrade from basic OCR to vision models (like Claude 3.5 Sonnet Vision) to read stamped notary seals, court clerk stamps, and hand-written filing dates that standard OCR misses.
- **Instant Deal Notifications**: Set up Discord or Slack webhooks that trigger immediately whenever a high-margin deal is found (e.g. *Equity > $150k + Deceased Owner + Sale Date within 30 days*).
- **Automated Website Change Alerts**: Set up lightweight daily test runs that check court login pages and alert us if a county changes its buttons or layout before our main scrapers run.

---

## 💻 Quickstart & Setup

### Prerequisites
- **Docker & Docker Compose** (Recommended) OR
- **Python 3.12+**, **Google Chrome**, and **Git** (For local development)

---

### Option 1: Running with Docker (Recommended)

1. **Clone the repo**:
   ```bash
   git clone https://github.com/your-username/Court-Scraper.git
   cd Court-Scraper
   ```

2. **Add your API keys**:
   ```bash
   cp .env.example .env
   # Add your SUPABASE_URL, SUPABASE_KEY, GROQ_API_KEY, and APIFY_API_KEY
   ```

3. **Start the containers**:
   ```bash
   docker compose up --build -d
   ```

4. **Open the live dashboard**:
   Go to **`http://localhost:5511`** in your browser to monitor cases and watch live logs.

---

### Option 2: Running Locally

1. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. **Install requirements**:
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Run the main scraper**:
   ```bash
   python main.py
   ```

4. **Run deed search workers in another terminal**:
   ```bash
   python deed_worker.py
   ```

---

## 🧪 Testing

The project includes **183 automated tests** that check data models, queue safety, file cleaners, and pipeline steps without hitting live websites:

```bash
# Run the full test suite
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

## 📂 Project Layout

```
Court-Scraper/
├── ai/                         # AI document reading (Groq, Claude, Mistral) & cost tracker
│   ├── llm_helper.py           # Pydantic schemas and prompts for legal text
│   ├── llm_cost_tracker.py     # Tracks token counts and API spend
│   └── ocr.py                  # Tesseract OCR for scanned PDF pages
├── browser/                    # Browser automation utilities
│   ├── browser_helpers.py      # Reliable wait conditions and tab management
│   └── OP.py                   # SalesWeb table scraper and auction parser
├── config/                     # Settings and environment validation
├── core/                       # Core data models, status enums, and runner contracts
├── counties/                   # Individual county portal adapters
│   ├── nj_processor.py         # New Jersey statewide eCourts automation
│   ├── broward_helpers.py      # Florida: Broward County portal adapter
│   ├── miami_helpers.py        # Florida: Miami-Dade County portal adapter
│   ├── palmbeach.py            # Florida: Palm Beach County portal adapter
│   └── ...                     # Additional Florida county adapters (15 total)
├── database/                   # Persistent storage & task queue
│   ├── deed_queue_db.py        # SQLite WAL task queue with crash recovery
│   └── supabase_service.py     # Supabase client and PostgreSQL RPC calls
├── deed_search/                # Separate deed searching subsystem
│   ├── downloader.py           # County deed site crawlers
│   ├── download_manager.py     # File verification and PDF storage
│   └── server.py               # Standalone deed search service
├── download/                   # File watchers and docket PDF cleaners
├── obituary_api/               # Deceased owner & heir search microservice
│   ├── client.py               # API client for main pipeline
│   ├── scraper.py              # Death registry and obituary crawler
│   ├── server.py               # Microservice web endpoint
│   └── state_normaliser.py     # Standardizes state abbreviations
├── pipeline/                   # Modular pipeline engine
│   ├── base.py                 # Pipeline blocks and signal types
│   └── orchestrator.py         # Multi-step retry logic and circuit breaker
├── tests/                      # 183 automated unit tests
├── app.py                      # Flask & Socket.IO live web dashboard
├── deed_worker.py              # Worker script consuming the SQLite deed queue
├── update_salesweb.py          # Standalone SalesWeb batch updater
├── update_zillow.py            # Standalone Zillow / Apify batch updater
├── Dockerfile                  # Container with Google Chrome & Xvfb virtual display
├── docker-compose.yml          # Docker compose config with 2GB shared memory
├── requirements.txt            # Python dependencies
└── main.py                     # Main application entry point
```

---


---

## 🎬 The Program in Action & Input Guide

### 1. The Program in Action

When you launch the system (`python main.py` or through Docker), it starts a real-time web dashboard at **`http://localhost:5511`**.

Instead of staring at a silent terminal, you get full live visibility into what every browser worker is doing:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  🏛️ COURT SCRAPER CONTROL CENTER                          [Workers: 2] [Status: RUNNING]        │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  Batch: palm_beach_cases.xlsx   | Total: 25 Cases | Completed: 14 | Failed: 0 | Remaining: 11    │
│  Progress: [██████████████████████████░░░░░░░░░░░░░░░░░░] 56%                                     │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  CASE DOCKET        COUNTY         PROPERTY ADDRESS          STATUS           CURRENT STEP       │
│  ─────────────────  ─────────────  ────────────────────────  ───────────────  ─────────────────  │
│  50-2023-CA-004121  Palm Beach, FL 108 Ocean Dr, Boca Raton  [COMPLETED]      Synced to Supabase │
│  F-014220-24        Essex, NJ      42 Elm St, Newark         [DOWNLOADING]    Doc 2/3 (Judgment) │
│  CACE-23-018942     Broward, FL    225 Sunset Blvd, Ft Laud  [AI PARSING]     Groq 70B Extract   │
│  2023-CA-001234-O   Orange, FL     780 Pine Ave, Orlando     [DEED SEARCH]    In WAL Queue (pos 2│
│  F-009841-24        Bergen, NJ     15 Maple Ave, Hackensack  [PRE-CHECKING]   SalesWeb Auction   │
│  50-2024-CA-001190  Palm Beach, FL 540 Lake Ave, W Palm Bch  [PENDING]        Waiting in line    │
├──────────────────────────────────────────────────────────────────────────────────────────────────┤
│  LIVE LOGS & DRIVER SNOOP                                                                        │
│  [18:42:01] Worker-1: Case 50-2023-CA-004121 Final Judgment parsed: $324,500 debt, Plaintiff BofA│
│  [18:42:05] Worker-1: Owner verified deceased. Obituary found: 3 surviving heirs listed          │
│  [18:42:10] Worker-2: Navigating to Essex County eCourts portal for docket F-014220-24...        │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

#### Case Lifecycle Statuses
Every case moves through clear, color-coded stages in the UI:
- ⚪ **`PENDING`**: Waiting in the queue for an available browser worker.
- 🔵 **`LOGGING IN`**: Browser authenticating into the county court portal.
- 🟡 **`PRE-CHECKING`**: Checking SalesWeb sheriff auctions and Zillow Zestimates to filter out low-equity properties before heavy scraping.
- 🟣 **`ENTERING DOCKET`**: Navigating to the case search page and loading the court docket.
- 🟢 **`DOWNLOADING`**: Downloading targeted legal PDFs (Complaints, Lis Pendens, Final Judgments).
- 🟠 **`AI PARSING`**: Running OCR and sending text to Groq / Claude to extract loan balances, judgment figures, and party names into structured JSON.
- 🟤 **`DEED SEARCH`**: Queued into the background SQLite WAL queue for county recorder deed verification.
- 🕊️ **`OBITUARY SEARCH`**: Querying death records and reading obituary text for surviving heirs and probate signals.
- ✅ **`COMPLETED`**: Case data, debts, deeds, and obituary findings safely saved in Supabase.
- ⚠️ **`SKIPPED`**: Case was closed/dismissed on docket, had no viable equity, or was already processed in a previous run.

---

### 2. Input Guide

The system accepts two forms of input: **The Case Spreadsheet** (which properties to research) and **The Runtime Settings** (how to run the automation).

#### A. The Case Input Spreadsheet (`.xlsx` or `.csv`)
You can drag-and-drop this file directly onto the web dashboard or place it in the `uploads/` directory.

| Column # | Column Name | Required? | Where It Is Used in the Pipeline | Example Value |
|---|---|---|---|---|
| **Column 1** | **Case Number / Docket** | **Required** | The primary search key. Entered into county court clerk search forms to locate the docket and find legal PDFs. If the number has formatting quirks or missing hyphens, the built-in AI normalizer cleans it up before searching. | `F-014220-24` (NJ)<br>`50-2023-CA-004121` (FL) |
| **Column 2** | **County / Jurisdiction** | **Required** | Tells the pipeline which county adapter to activate, which court portal URL to hit, and which login and navigation rules to apply. | `New Jersey`, `Palm Beach`, `Broward`, `Miami-Dade`, `Orange` |
| **Column 3** | **Property Address** | **Optional** | If provided, immediately triggers Zillow Zestimate lookups and SalesWeb auction checks *before* opening browser tabs. If left blank, the scraper extracts the address directly from the court Lis Pendens or Complaint PDF. | `42 Elm St, Newark, NJ 07102` |
| **Column 4** | **SalesWeb County** | **Optional** | Used specifically for New Jersey cases. Targets the exact county dropdown on the SalesWeb sheriff auction site to pull upset bids, sale dates, and bank attorneys. Defaults to Column 2 if blank. | `Essex`, `Bergen`, `Monmouth` |
| **Column 5** | **Status** | **Optional** | Used for resuming runs. If a row is marked as `Processed` or `Completed`, the scraper skips it automatically, saving time, proxy bandwidth, and AI tokens. | `Processed`, `Pending` |

#### B. Runtime Settings (`settings.json` or Web UI Modal)
Configurable through the **Settings Modal** on the dashboard or directly in `settings.json`:

| Setting Key | Type | Required? | Where It Is Used & What It Does | Default Value |
|---|---|---|---|---|
| `input_file` | String | **Required** | File path to the `.xlsx` or `.csv` spreadsheet containing the list of cases to scrape. | `uploads/palm_beach.xlsx` |
| `batch_name` | String | **Optional** | A human-readable label for the run. Used to name output folders, database batch tags, and exported Excel summaries. Defaults to the input filename. | `palm_beach` |
| `output_folder` | String | **Optional** | Directory where downloaded PDFs, screenshots, and summary Excel files are saved. If empty, creates a timestamped folder automatically. | `""` (auto-created) |
| `keywords` | String | **Optional** | Comma-separated list of document names. The regex scanner looks for these in court docket descriptions to decide which PDFs to download. | `Complaint, Final Judgment, Lis Pendens, Vacate, Additional Sums` |
| `unwanted_keywords` | String | **Optional** | Document keywords to ignore. Prevents downloading administrative clutter like certificate of service or military affidavits. | `Proof of mailing, Military affidavit, Foreclosure judgment notice` |
| `headless_mode` | Boolean | **Optional** | If `true`, runs Chrome in the background. If `false`, opens a visible Chrome window (useful for debugging). Inside Docker, always runs via virtual Xvfb display. | `false` |
| `max_workers` | Integer | **Optional** | Number of browser instances running in parallel. Set to 1–4 depending on your CPU and RAM capacity. | `1` |
| `skip_closed_cases` | Boolean | **Optional** | When enabled, immediately skips any case that the court portal marks as closed, dismissed, or settled. | `false` |
| `skip_business` | Boolean | **Optional** | Filters out corporate or commercial debtors (e.g. LLCs, Inc.) so you only spend time on residential homeowner leads. | `false` |
| `llm_service` | String | **Optional** | Which AI provider to use for parsing legal PDFs: `"anthropic"`, `"groq"`, or `"mistral"`. | `"anthropic"` |
| `llm_api_key` | String | **Required for AI** | API key for the selected LLM provider. If omitted, documents are still downloaded and deeds are searched, but AI JSON parsing is skipped. | `"sk-ant-..."` |

---

