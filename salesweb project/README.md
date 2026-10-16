# Foreclosure Scraper

Automated tool for sourcing real estate foreclosure leads from [salesweb.civilview.com](https://salesweb.civilview.com), enriched with Zillow property data via Apify.

## Features

- Scrapes open/sold foreclosure listings by county and state
- Two-level parallelism for fast data collection (month threads + listing threads)
- Zillow Zestimate enrichment via rotating Apify API keys
- Exports to Excel (`.xlsx`)

## Project Structure

```
foreclosure-scraper/
├── src/
│   ├── scrapers/
│   │   └── civilview.py      # Main scraper class
│   ├── utils/
│   │   ├── zillow.py         # Apify/Zillow integration
│   │   ├── parsers.py        # Text extraction helpers
│   │   └── export.py         # Excel/CSV export
│   └── config.py             # Config via environment variables
├── tests/                    # Pytest unit tests
├── .github/
│   ├── workflows/ci.yml      # GitHub Actions CI pipeline
│   └── PULL_REQUEST_TEMPLATE.md
├── run.py                    # CLI entry point
├── .env.example              # Environment variable template
└── requirements.txt
```

## Setup

```bash
git clone https://github.com/your-org/foreclosure-scraper.git
cd foreclosure-scraper
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your Apify API keys
```

## Usage

```bash
# Scrape open listings in New Jersey
python run.py --state NJ --status open

# Scrape both open and sold listings in NJ and PA
python run.py --state NJ --state PA --status both

# Custom output path
python run.py --state NJ --output output/NJ_$(date +%Y%m%d).xlsx
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--state` | required | State abbreviation(s), repeatable |
| `--status` | `open` | `open`, `sold`, or `both` |
| `--output` | auto | Excel output file path |
| `--delay` | `2` | Seconds between requests |
| `--workers` | `5` | Parallel worker threads |

## Configuration

All secrets are loaded from environment variables (see `.env.example`):

| Variable | Description |
|----------|-------------|
| `APIFY_API_KEY_1` … `N` | Apify API keys (rotated randomly) |
| `SCRAPER_DELAY` | Request delay in seconds |
| `OUTPUT_DIR` | Directory for output files |

## Running Tests

```bash
pytest tests/ -v
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Legal Notice

This tool is intended for legitimate real estate research purposes only.
Always comply with the target website's Terms of Service and applicable laws.
