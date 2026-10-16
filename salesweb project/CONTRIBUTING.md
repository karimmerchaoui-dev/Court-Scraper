# Contributing

## Getting Started

```bash
git clone https://github.com/your-org/foreclosure-scraper.git
cd foreclosure-scraper
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your API keys
```

## Workflow

1. Branch off `develop`: `git checkout -b feature/your-feature`
2. Make changes, add tests in `tests/`
3. Run `pytest tests/ -v` and `ruff check src/ tests/`
4. Open a PR into `develop` with a clear description

## Commit Style (Conventional Commits)

```
feat: add support for PA county scraping
fix: handle missing zestimate gracefully
chore: bump apify-client to 1.8.0
docs: update README usage section
```

## Code Style

- Formatter: `ruff format`
- Linter: `ruff check`
- Type hints encouraged on all public functions
