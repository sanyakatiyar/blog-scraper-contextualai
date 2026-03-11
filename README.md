# Blog Scraper → Contextual AI Pipeline

Automated pipeline that scrapes AI/ML blog posts and ingests them into a [Contextual AI](https://contextual.ai) datastore to power a multi-source research agent.

## Overview

An automated content ingestion pipeline that keeps a Contextual AI datastore fresh with the latest AI/ML content. The scraper runs on a schedule, pulls new articles, filters out anything already seen, and uploads only what's new.

**How it works:**
1. Fetch articles from configured sources - RSS feeds first, HTML scraping as fallback
2. Filter by date, word count, and topic relevance
3. Deduplicate against a persistent URL registry so nothing gets uploaded twice
4. Convert each article to a structured text document and upload to Contextual AI
5. Commit the updated URL registry back to the repo so the next run picks up where this one left off

## Project Structure

```
blog-scraper/
├── .github/workflows/
│   ├── scrape-blogs.yml       # Scraper - runs every 3 days + manual trigger
│   └── ci.yml                 # Code quality - lint, format, type-check
├── config/
│   ├── sources.yaml           # Scraper source config
│   ├── agent.yaml             # Contextual AI Agent Composer YAML (multi-source)
│   └── settings.py            # App settings (env vars)
├── src/
│   ├── scrapers/
│   │   ├── unified_scraper.py # RSS-first unified scraper
│   │   └── __init__.py
│   ├── storage/
│   │   ├── contextual_uploader.py  # Uploads to Contextual AI
│   │   └── local_storage.py        # Saves articles locally as JSON
│   └── utils/
├── scripts/
│   └── run_unified.py         # Main entry point
├── data/
│   └── scraped_urls.json      # Persistent URL registry (deduplication)
├── blogs-test.yaml            # Test agent YAML (blogs datastore only)
├── .env.example
├── requirements.txt
└── pyproject.toml
```

## Quick Start

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Add CONTEXTUAL_API_KEY and CONTEXTUAL_DATASTORE_ID to .env
```

## Running the Scraper

```bash
# List all available sources
python scripts/run_unified.py --list

# Scrape all sources (50 articles each, 60-day lookback)
python scripts/run_unified.py

# Scrape a specific source
python scripts/run_unified.py --source anthropic_research --max-articles 10

# Dry run - scrape but skip upload
python scripts/run_unified.py --dry-run --max-articles 5

# Force re-scrape already seen URLs
python scripts/run_unified.py --source langchain --force-rescrape --max-articles 10

# Custom lookback window
python scripts/run_unified.py --max-articles 50 --lookback-days 120

# Full historical load (no date filter)
python scripts/run_unified.py --max-articles 100 --lookback-days 0 --force-rescrape

# RSS sources only (most reliable)
python scripts/run_unified.py --rss-only
```

## Environment Variables

```bash
CONTEXTUAL_API_KEY=your_api_key_here
CONTEXTUAL_DATASTORE_ID=your_datastore_id_here

# Optional
SCRAPE_DELAY_SECONDS=2
MAX_ARTICLES_PER_SOURCE=50
LOG_LEVEL=INFO
DRY_RUN=false
FORCE_RESCRAPE=false
```

## Document Format

Each article is ingested as `{source}_{YYYY-MM-DD}_{hash}.txt`:

```
# Article Title | 2025-01-15

## Metadata
- Source: LangChain Blog
- URL: https://...
- Author: Harrison Chase
- Tags: agents, rag, langchain
- Word Count: 1200

## Summary
Brief summary...

## Content
Full article text...
```

Custom metadata (`source`, `url`, `author`, `published_date`, `tags`, `word_count`) is attached to each document for filtering in the agent.

## Agent YAML

`config/agent.yaml` defines a multi-source Contextual AI research agent:

- **QueryMultiturnStep** - resolves pronouns in follow-up queries
- **AgenticResearchStep** - multi-turn research loop with:
  - `search_docs` - searches all 3 datastores
  - `web_search` - live web fallback (Gemini 2.5 Flash)
  - `analyze_file` - analyzes user-uploaded files
- **GenerateFromResearchStep** - synthesizes final response

`blogs-test.yaml` is a simplified single-datastore version for testing the blogs datastore.

Deploy by uploading the YAML to the Contextual AI Agent Composer.

## GitHub Actions

- **`scrape-blogs.yml`** - runs every 3 days at 6 AM UTC, manual trigger with inputs: `source`, `rss_only`, `dry_run`, `max_articles`, `lookback_days`. Secrets required: `CONTEXTUAL_API_KEY`, `CONTEXTUAL_DATASTORE_ID`.
- **`ci.yml`** - runs on every push/PR: ruff lint, black format check, mypy, pytest.

## Adding a New Source

1. Add an entry to `config/sources.yaml` with `type: rss` or `type: html`
2. Run `python scripts/run_unified.py --list` to verify it appears
3. Test with `--source your_source_name --dry-run`
