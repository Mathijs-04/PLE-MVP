# Setup

Developer onboarding for running Warhammer Rule Assistant locally.

## Prerequisites

- PHP 8.3+
- Composer
- Node.js (for Vite)
- Python 3.x
- OpenAI API key

## First-Time Setup

1. Clone the repository and install PHP/frontend dependencies:

   ```bash
   composer setup
   ```

   This runs `composer install`, copies `.env.example` to `.env` if needed, generates an app key, migrates the database, runs `npm install`, and builds frontend assets.

2. Create the SQLite database if it does not exist:

   ```bash
   touch database/database.sqlite
   php artisan migrate
   ```

   The `composer setup` script runs migrations automatically; repeat this step only if the database file is missing.

3. Install Python dependencies (a virtual environment is recommended):

   ```bash
   pip install -r python/requirements.txt
   ```

4. Configure environment variables — see the table below.

5. Build FAISS vector indexes from the markdown rules files:

   ```bash
   python python/build_index.py --game aos --game wh40k
   ```

   This requires `OPENAI_API_KEY`. Indexes are written to `python/indexes/` (gitignored).

## Environment Variables

Project-specific variables beyond the standard Laravel defaults:

| Variable | Used by | Default / notes |
|----------|---------|-----------------|
| `OPENAI_API_KEY` | Python (`rag_engine.py`, `build_index.py`) | Required for indexing and chat answers |
| `AI_SERVICE_URL` | Laravel (`config/services.php`) | `http://127.0.0.1:8001` |

Add these to your `.env` file. See `.env.example` for the variable names.

## Running Locally

Two processes must run at the same time:

**Terminal 1 — Laravel + Vite + queue:**

```bash
composer run dev
```

**Terminal 2 — Python AI service:**

```bash
python python/web_rules_qa.py
```

The FastAPI service listens on `http://127.0.0.1:8001`. Interactive API docs are available at `http://127.0.0.1:8001/docs` while the service is running.

Ensure `AI_SERVICE_URL` in `.env` matches the Python service address.

## Verification

- Open `/` to use the rules chat.
- Open `/rules?game=aos` to view the core rules PDF viewer.
- Run Laravel tests: `composer test`
- Run Python tests: `python -m unittest discover -s python/tests`

## Troubleshooting

**Chat returns an AI service error**

Confirm the Python service is running and that `AI_SERVICE_URL` in `.env` points to it (default `http://127.0.0.1:8001`).

**Python service fails at startup with missing indexes**

Build indexes first:

```bash
python python/build_index.py --game aos --game wh40k
```

**Index build fails**

Confirm `OPENAI_API_KEY` is set in `.env`. Index building calls OpenAI's embedding API.

**Fresh clone without pre-built indexes**

The markdown rules files are in the repository, but FAISS indexes are not. Run `build_index.py` after setup (see step 5 above).
