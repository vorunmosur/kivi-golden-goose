# Run Kivi Golden Goose

This is the shortest reviewer path for the final V2 implementation.

## Requirements

- Windows, macOS or Linux
- Python 3.12
- Ollama
- Qwen3.5 9B
- nomic-embed-text

A GPU is strongly recommended for local model inference. CPU execution works but is substantially slower.

No paid model API key is required.

---

## 1. Install

### PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt

ollama pull qwen3.5:9b
ollama pull nomic-embed-text
```

Ensure Ollama is running. On systems without the background application:

```powershell
ollama serve
```

In a new terminal:

```powershell
$env:KIVI_PROVIDER="ollama"
$env:KIVI_OLLAMA_URL="http://localhost:11434"
$env:KIVI_LLM_MODEL="qwen3.5:9b"
$env:KIVI_EMBEDDING_MODEL="nomic-embed-text"
$env:KIVI_DB_PATH="./kivi-v2.db"
```

`.env.example` documents the same settings. Environment variables are read at process startup.

---

## 2. Initialize the database

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

---

## 3. Start Kivi

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open:

`http://127.0.0.1:8000`

The product surfaces are:

- **Learn**
- **Hey Kivi**
- **Memory**
- **Why?**

---

## 4. Five-minute reviewer walkthrough

### A. Learn current state

In Learn:

> Rajeev is my manager.

Ask Hey Kivi:

> Who is my current manager?

Inspect the resulting memory and source evidence.

### B. Introduce uncertainty

Learn:

> Priya might become my manager next month.

Ask again:

> Who is my current manager?

The tentative future statement should not silently replace confirmed current state.

### C. Confirm a change

Learn:

> Priya officially took over as my manager today.

Ask again:

> Who is my current manager?

Inspect Memory / Why? to see the lifecycle transition rather than only the final sentence.

### D. Test distributed knowledge

Learn separate interactions such as:

> Project Aurora is due Friday.

> Aurora uses FastAPI for the backend.

Then ask:

> What do you know about Aurora's deadline and backend technology?

The answer should combine independently supported facts while retaining their evidence.

### E. Test correction

Learn:

> Correction: Aurora's deadline moved to Saturday.

Ask the same question again.

The current answer should use Saturday rather than the stale Friday state.

### F. Test grounded drafting

Learn:

> Keep my work updates concise and use bullet points.

Ask:

> Draft a concise update saying Aurora is due Saturday and uses FastAPI.

The presentation preference may affect formatting, but every factual proposition must still come from supplied evidence.

### G. Test unsupported information

Ask for personal information that was never supplied.

Kivi should abstain rather than invent it.

### H. Test forgetting

Use Memory to forget a retained item and query it again.

Old raw interaction history behind the forget boundary should not silently restore the forgotten fact.

---

## 5. Run the automated tests

Run the primary suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_migrations.py --basetemp=.pytest_tmp
```

Final verified result:

```text
162 passed
```

Run migrations separately:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_migrations.py --basetemp=.pytest_migrations
```

Final verified result:

```text
3 passed
```

Total final verification:

```text
165 passed, 0 failed
```

Dependency/API deprecation warnings may be printed during the suite.

---

## 6. Inspect the preserved final evaluation

The final clean model-backed 500-record run is preserved at:

```text
eval/final-hardening-clean-500/
```

Its summary records:

```text
records:              500 / 500
ingestion_failures:   0
missing_provenance:   0
retained_secrets:     0
median_ingestion:     46.297 s
p95_ingestion:        73.051 s
local_provider_cost:  $0
```

Local provider cost excludes hardware and electricity.

This is a pipeline-integrity run. It is **not** labeled as 500/500 semantic accuracy.

The post-500 frozen-state semantic challenge is preserved separately. No re-ingestion was used for that challenge.

---

## 7. Optional: run the semantic challenge

A reviewer does **not** need to rerun the full 500-record ingestion to inspect the implementation.

The full local-model corpus run is expensive and can take hours depending on hardware.

For development/evaluation scripts, use a fresh output directory rather than overwriting preserved evidence.

The repository includes:

```text
eval/run_v2_eval.py
eval/run_longitudinal.py
eval/post500_semantic_challenge.py
```

The post-500 challenge expects an existing database state and therefore should not be treated as a fresh-install smoke test.

---

## 8. API / audit surfaces

Useful endpoints include:

```text
/api/memories
/api/decisions
/api/traces
/api/entities
/api/interactions/{id}
```

The UI exposes the same core inspection model through Memory and Why?.

Audit inspection may show evidence associated with forgotten state. Hey Kivi retrieval must not use evidence across the applicable forget boundary.

---

## 9. Generic history import

Learn supports:

- JSON arrays
- JSON objects containing record arrays
- JSONL
- CSV

Required field:

```text
raw_asr
```

Recommended fields:

```text
formatted_output
timestamp
app
style
session_id
metadata
```

`formatted_text` and `llm_formatted_output` are also accepted where supported by the importer.

Missing contextual fields use generic defaults. The memory system does not depend on a fixed name, profession, project or predicate whitelist.

Imports are processed chronologically.

Invalid rows and model failures remain inspectable rather than disappearing silently.

---

## 10. Reset

Use the application's Reset state control, or:

```text
POST /api/reset
```

Evaluation should use a separate database from manual application testing.

---

## Known limits

The final implementation is intentionally narrow:

- one local user;
- no authentication;
- no connected-app sending;
- local Qwen inference can be slow;
- exact vector scanning is appropriate only at this scale;
- tentative evidence is conservatively handled but confirmation-status explanations can be richer;
- arbitrary deep graph traversal is not guaranteed;
- verification reduces unsupported generation but cannot provide a formal proof of semantic correctness.

For design invariants and implementation rationale, see:

- `README.md`
- `docs/V2_CONTRACT.md`
- `docs/GROUNDED_REALIZATION.md`
