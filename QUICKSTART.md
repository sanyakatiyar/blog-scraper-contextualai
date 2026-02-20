# Quick Start Guide

This guide will help you get the blog scraper running quickly for local testing.

## 🎯 Architecture: RSS-First

This scraper prioritizes **RSS feeds** over HTML scraping:

| Method | Reliability | Sources |
|--------|-------------|---------|
| 📡 RSS | ⭐⭐⭐⭐⭐ High | LangChain, HuggingFace, Anthropic (via community feeds) |
| 🌐 HTML | ⭐⭐⭐ Medium | LlamaIndex, Pinecone, Weaviate, Cohere |

RSS feeds are:
- More stable (don't break when sites redesign)
- Structured (no CSS selector guessing)
- Faster (smaller payload)

## 1. Setup (One Time)

```bash
# Clone or navigate to the project
cd blog-scraper

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment template
cp .env.example .env
```

## 2. Test Locally

### List Available Sources
```bash
python scripts/run_unified.py --list
```

Output:
```
======================================================================
AVAILABLE SOURCES
======================================================================

📡 RSS Sources (Preferred - More Reliable):
--------------------------------------------------
  ✅ langchain                 - LangChain Blog
  ✅ huggingface               - Hugging Face Blog
  ✅ anthropic_research        - Anthropic Research
  ✅ anthropic_news            - Anthropic News
  ✅ anthropic_engineering     - Anthropic Engineering

🌐 HTML Sources (Fallback - May Break):
--------------------------------------------------
  ⚠️  llamaindex               - LlamaIndex Blog
  ⚠️  pinecone                 - Pinecone Learn
  ⚠️  weaviate                 - Weaviate Blog
  ⚠️  cohere                   - Cohere Blog
```

### Quick Test (RSS Only - Most Reliable)
```bash
python scripts/run_unified.py --rss-only --dry-run --max-articles 5
```

### Scrape Single Source
```bash
python scripts/run_unified.py --source langchain --dry-run
```

### Scrape All Sources
```bash
python scripts/run_unified.py --dry-run
```

### Check Output
```bash
# View scraped articles
ls -la data/raw/articles/

# View a specific article
cat data/raw/articles/langchain/*.json | head -100

# View scrape report
cat data/raw/scrape_report.json
```

## 3. Run Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## 4. Configure for Upload (Optional)

For uploading to Contextual AI:

```bash
# Edit .env and add your credentials:
CONTEXTUAL_API_KEY=your_api_key_here
CONTEXTUAL_DATASTORE_ID=your_datastore_id_here  # Optional
```

Then run without `--dry-run`:
```bash
python scripts/run_unified.py --rss-only
```

## 5. GitHub Actions Setup

1. Go to your GitHub repo Settings → Secrets and variables → Actions

2. Add these secrets:
   - `CONTEXTUAL_API_KEY`: Your Contextual AI API key
   - `CONTEXTUAL_DATASTORE_ID`: Your datastore ID (optional)

3. The workflow will run:
   - Daily at 6 AM UTC (scheduled)
   - On push to main
   - Manually via workflow_dispatch

### Manual Trigger Options
- **source**: Specific source to scrape
- **rss_only**: Only reliable RSS sources
- **dry_run**: Test without uploading
- **max_articles**: Limit per source

## 6. RSS Feed Sources

The scraper uses these RSS feeds:

| Source | RSS URL |
|--------|---------|
| LangChain | `https://blog.langchain.dev/rss/` |
| HuggingFace | `https://huggingface.co/blog/feed.xml` |
| Anthropic Research | Community feed from [Olshansk/rss-feeds](https://github.com/Olshansk/rss-feeds) |
| Anthropic News | Community feed |
| Anthropic Engineering | Community feed |

For sites without RSS (LlamaIndex, Pinecone, etc.), the scraper falls back to HTML parsing.

## Common Issues

### Rate Limiting
If you see 429 errors, increase the delay:
```bash
export SCRAPE_DELAY_SECONDS=5
python scripts/run_unified.py --source anthropic_research --dry-run
```

### RSS Feed Empty
Some community feeds may occasionally be empty. Try again later or use `--html-only` mode.

### Missing Dependencies
```bash
pip install --upgrade -r requirements.txt
```

## Project Structure

```
blog-scraper/
├── config/
│   ├── sources.yaml    # RSS + HTML source definitions
│   └── settings.py     # Global settings
├── src/
│   ├── scrapers/
│   │   ├── unified_scraper.py  # ⭐ Main scraper (RSS-first)
│   │   └── ...                  # Legacy per-source scrapers
│   ├── storage/        # Local + Contextual AI storage
│   └── utils/          # Logging, rate limiting
├── scripts/
│   ├── run_unified.py  # ⭐ Recommended entry point
│   └── run_scraper.py  # Legacy script
├── data/
│   └── raw/            # Scraped data (gitignored)
└── tests/
```

## Next Steps

1. ✅ Test with `--rss-only --dry-run` (most reliable)
2. 📝 Set up Contextual AI credentials
3. 🚀 Run full pipeline
4. ⏰ Set up GitHub Actions for daily scraping
5. 🔧 Customize sources in `config/sources.yaml`
