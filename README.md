# Context Crew - Blog Scraping Pipeline

A comprehensive blog scraping pipeline for the Context Crew capstone project. This pipeline collects blog posts from reputable sources in the LLM, RAG, agentic systems, and context-engineering domains, storing them in Contextual AI's datastore.

## 🎯 Target Blog Sources

Based on the project proposal focusing on RAG, context engineering, and agent workflows, we scrape the following sources:

### Primary Sources (High Signal)
| Source | URL | Focus Area |
|--------|-----|------------|
| Anthropic Research | https://www.anthropic.com/research | Claude, safety, interpretability |
| LlamaIndex Blog | https://www.llamaindex.ai/blog | RAG frameworks, indexing |
| LangChain Blog | https://blog.langchain.dev | Chains, agents, RAG |
| Hugging Face Blog | https://huggingface.co/blog | Models, transformers, NLP |
| OpenAI Blog | https://openai.com/blog | GPT, agents, research |
| Contextual AI Blog | https://contextual.ai/blog | RAG, grounded generation |

### Secondary Sources (Technical Deep-Dives)
| Source | URL | Focus Area |
|--------|-----|------------|
| Pinecone Blog | https://www.pinecone.io/learn | Vector databases, embeddings |
| Weaviate Blog | https://weaviate.io/blog | Vector search, RAG |
| Cohere Blog | https://cohere.com/blog | NLP, embeddings, RAG |
| AI21 Labs Blog | https://www.ai21.com/blog | Language models |

## 📁 Project Structure

```
blog-scraper/
├── .github/
│   └── workflows/
│       └── scrape-blogs.yml       # GitHub Actions workflow
├── src/
│   ├── __init__.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base_scraper.py        # Abstract base class
│   │   ├── anthropic_scraper.py   # Anthropic blog scraper
│   │   ├── llamaindex_scraper.py  # LlamaIndex blog scraper
│   │   ├── langchain_scraper.py   # LangChain blog scraper
│   │   ├── huggingface_scraper.py # Hugging Face blog scraper
│   │   └── rss_scraper.py         # Generic RSS scraper
│   ├── processors/
│   │   ├── __init__.py
│   │   ├── content_cleaner.py     # HTML cleaning, text extraction
│   │   └── metadata_extractor.py  # Extract structured metadata
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── local_storage.py       # JSON file storage
│   │   └── contextual_uploader.py # Contextual AI datastore upload
│   └── utils/
│       ├── __init__.py
│       ├── rate_limiter.py        # Respect rate limits
│       └── logger.py              # Structured logging
├── config/
│   ├── sources.yaml               # Blog source configuration
│   └── settings.py                # Global settings
├── data/
│   └── raw/                       # Raw scraped data (gitignored)
├── tests/
│   ├── __init__.py
│   ├── test_scrapers.py
│   └── test_processors.py
├── scripts/
│   ├── run_scraper.py             # Main entry point
│   └── upload_to_contextual.py    # Upload to Contextual AI
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Contextual AI API key
- GitHub repository (for CI/CD)

### Local Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/context-crew-blog-scraper.git
   cd context-crew-blog-scraper
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run the scraper locally**
   ```bash
   # Scrape all sources
   python scripts/run_scraper.py --all

   # Scrape specific source
   python scripts/run_scraper.py --source anthropic

   # Dry run (no upload)
   python scripts/run_scraper.py --all --dry-run
   ```

### Testing Locally

```bash
# Run all tests
pytest tests/ -v

# Run specific test
pytest tests/test_scrapers.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

## ⚙️ Configuration

### Environment Variables (`.env`)

```bash
# Contextual AI
CONTEXTUAL_API_KEY=your_api_key_here
CONTEXTUAL_DATASTORE_ID=your_datastore_id_here

# Optional: Rate limiting
SCRAPE_DELAY_SECONDS=2
MAX_ARTICLES_PER_SOURCE=50

# Optional: Logging
LOG_LEVEL=INFO
```

### Source Configuration (`config/sources.yaml`)

```yaml
sources:
  anthropic:
    name: "Anthropic Research"
    base_url: "https://www.anthropic.com"
    blog_path: "/research"
    scraper_class: "AnthropicScraper"
    enabled: true
    max_articles: 50
    
  llamaindex:
    name: "LlamaIndex Blog"
    base_url: "https://www.llamaindex.ai"
    blog_path: "/blog"
    scraper_class: "LlamaIndexScraper"
    enabled: true
    max_articles: 50
```

## 📊 Data Schema

Each scraped article is stored with the following schema:

```json
{
  "id": "anthropic_2024_01_15_claude_3",
  "source": "anthropic",
  "source_name": "Anthropic Research",
  "url": "https://www.anthropic.com/research/claude-3",
  "title": "Introducing Claude 3",
  "author": "Anthropic Team",
  "published_date": "2024-01-15T00:00:00Z",
  "scraped_at": "2024-01-20T12:00:00Z",
  "content_text": "Full article text...",
  "content_html": "<html>...</html>",
  "summary": "First 500 chars...",
  "tags": ["claude", "announcement", "models"],
  "word_count": 1500,
  "metadata": {
    "reading_time_minutes": 7,
    "has_code_blocks": true,
    "has_images": true
  }
}
```

## 🔄 GitHub Actions Pipeline

The pipeline runs automatically on a schedule and can be triggered manually.

### Workflow Triggers
- **Scheduled**: Daily at 6 AM UTC
- **Manual**: Via workflow_dispatch
- **On Push**: To main branch (for testing changes)

### Workflow Steps
1. Checkout code
2. Set up Python environment
3. Install dependencies
4. Run scrapers for all enabled sources
5. Validate scraped data
6. Upload to Contextual AI datastore
7. Generate summary report
8. Commit updated metadata (optional)

## 📝 Adding a New Blog Source

1. **Create a new scraper class** in `src/scrapers/`:
   ```python
   from .base_scraper import BaseScraper
   
   class NewBlogScraper(BaseScraper):
       def get_article_urls(self) -> list[str]:
           # Implement URL discovery
           pass
       
       def scrape_article(self, url: str) -> dict:
           # Implement article scraping
           pass
   ```

2. **Add configuration** to `config/sources.yaml`

3. **Register the scraper** in `src/scrapers/__init__.py`

4. **Write tests** in `tests/test_scrapers.py`

## 🛡️ Rate Limiting & Ethics

- Respects `robots.txt` for all sources
- Implements configurable delays between requests (default: 2 seconds)
- Uses appropriate User-Agent headers
- Caches already-scraped URLs to avoid duplicates
- Stores HTML snapshots for audit purposes

## 📈 Monitoring

The pipeline logs:
- Number of articles scraped per source
- Success/failure rates
- Upload status to Contextual AI
- Any errors or warnings

Logs are available in GitHub Actions workflow runs.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details.
