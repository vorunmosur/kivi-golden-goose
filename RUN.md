# Kivi Golden Goose — Runbook

Primary review method: **local single-process web application + SQLite**.

## 1. Runtime

- **Python 3.12.x recommended and used for the Windows validation path.**
- Python 3.11 is also expected to work.
- Python 3.14 is not recommended for this pinned environment because some dependency versions may fall back to native compilation on Windows.
- No Node, Docker, Postgres, or external database is required.

## 2. Create the environment

### macOS / Linux

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Windows PowerShell

```powershell
py -3.12 -m venv .venv
```

If PowerShell allows venv activation:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If script activation is blocked by Windows execution policy, **do not change machine policy just for this repo**. Call the venv interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

All commands below can likewise replace `python` with `.\.venv\Scripts\python.exe` on Windows.

## 3. Provider configuration

Kivi uses an **OpenAI-compatible provider interface**. The preferred generic environment variables are:

- `KIVI_LLM_API_KEY`
- `KIVI_LLM_MODEL`
- `KIVI_EMBEDDING_MODEL`
- `KIVI_LLM_BASE_URL`
- `KIVI_DB_PATH` (default `./kivi.db`)
- `KIVI_LLM_MAX_RETRIES` (default `3`)
- `KIVI_LLM_RETRY_BASE_SECONDS` (default `0.6`)
- `KIVI_INPUT_COST_PER_1M` / `KIVI_OUTPUT_COST_PER_1M` (optional evaluation cost calculation)

`OPENAI_API_KEY` remains accepted as a backward-compatible fallback, but the memory architecture is not tied to OpenAI.

### Example: OpenAI-compatible OpenAI endpoint

```bash
export KIVI_LLM_API_KEY="..."
export KIVI_LLM_BASE_URL="https://api.openai.com/v1"
export KIVI_LLM_MODEL="gpt-5-mini"
export KIVI_EMBEDDING_MODEL="text-embedding-3-small"
export KIVI_DEMO_MODE="false"
```

### Example: Google Gemini OpenAI-compatible endpoint

Use model names available to the Google AI project at run time. The final manual live smoke path was successfully exercised with Gemini through Google's OpenAI-compatible endpoint.

```powershell
$env:KIVI_LLM_API_KEY="..."
$env:KIVI_LLM_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
$env:KIVI_LLM_MODEL="gemini-3.8-flash"
$env:KIVI_EMBEDDING_MODEL="gemini-embedding-001"
$env:KIVI_DEMO_MODE="false"
```

Without a provider key, leave `KIVI_DEMO_MODE=true` to exercise the deliberately limited deterministic regression path.

If a provider returns HTTP `429`, the client retries with bounded backoff and then surfaces the quota error. This is expected when a free-tier project is exhausted; do not interpret it as a memory-engine failure.

If `KIVI_LLM_BASE_URL` is blank or not an absolute `http(s)` URL, the provider now fails immediately with a clear configuration error before sending any request.

## 4. Migrate and verify

```bash
python -m alembic upgrade head
python -m pytest -q
```

Expected repository test count at submission lock: **19 passed**.

## 5. Generate the development corpus

```bash
python scripts/generate_corpus.py
```

This writes `data/dev_corpus.jsonl` with ~500 transcript-like records including known Styles, missing/unknown Style, corrections, secrets, temporary information, preferences, facts, and irrelevant chatter.

## 6. Run the reproducible offline regression

Run without a provider key / with demo mode enabled:

```bash
python scripts/generate_corpus.py
python eval/run_eval.py
```

Generated result: `eval/results.json`.

The checked-in result is intentionally labeled **offline_regression**. It tests persistence, lifecycle rules, deterministic guardrails, provenance, retrieval plumbing, and grounded refusal behavior. It is **not** presented as a measurement of LLM semantic quality.

## 7. Run the live semantic validation suite

With a provider configured and `KIVI_DEMO_MODE=false`:

```bash
python eval/run_live_semantic_suite.py
```

This is a small, intentionally difficult live suite rather than a costly 500-call benchmark. It checks:

- manager creation + correction,
- scoped email preference,
- a global fact mentioned in developer context,
- weak inference handling,
- credential rejection,
- temporary/episodic information,
- explicit forget/delete,
- unsupported-question refusal,
- synthesis across distributed evidence,
- missing/unknown Style.

It writes `eval/live_semantic_results.json`. If no API key is configured, it exits cleanly with a skip message instead of silently substituting offline fixtures.

Transient upstream `429/500/502/503/504` responses and transport timeouts are retried with bounded exponential backoff. Permanent authentication/not-found errors are not retried.

## 8. Run the full model-backed 500-record evaluator (optional but supported)

With a provider configured:

```bash
python scripts/generate_corpus.py
python eval/run_eval.py
```

The same evaluator then uses the real semantic extractor and grounded answerer. Per-case failures remain visible in `pipeline_errors`, `admission_evaluation.failures`, and the inspectable cases. For a free-tier provider, check rate limits before running all 500 records.

## 9. Start the normal-user product

```bash
python -m uvicorn app.main:app --reload
```

Open:

`http://127.0.0.1:8000`

The product experience begins and ends in this interface; a terminal or database console is not required for normal use.

Suggested demo:

1. **Learn** → Work Messaging: `Rajeev is my manager.`
2. **Learn** → Developer: `I'm working on Golden Goose.`
3. **Learn** → Developer: `Use this API key: sk-...` and observe that it is rejected.
4. Open a fresh **Hey Kivi** session and ask `Who is my manager?`
5. Add `Correction: Priya is my manager now.` and ask again.
6. Open **Memory** to inspect provenance and delete a memory.
7. Open **Why?** to inspect admission/query traces without requiring a developer console.

## 10. Import another corpus / hidden evaluation data

The UI/API accepts JSONL or JSON at `POST /api/import` as multipart file upload. Each record may include:

`raw_asr`, `formatted_output`, `timestamp`, `app`, `style`, `session_id`, `metadata`.

`style` and `app` may be absent, null, empty, or unfamiliar. They are context hints; extraction does **not** depend on a known Style.

```bash
curl -F "file=@data/dev_corpus.jsonl" http://127.0.0.1:8000/api/import
```

## 11. Inspect memory and traces

- Normal-user Memory surface: app → **Memory**
- Explainability surface: app → **Why?**
- APIs: `/api/memories`, `/api/decisions`, `/api/traces`
- Offline evaluation: `eval/results.json`
- Optional live suite result: `eval/live_semantic_results.json`
- SQLite database: `kivi.db`

## 12. Reset

UI: **Reset state**

or:

```bash
curl -X POST http://127.0.0.1:8000/api/reset
```
