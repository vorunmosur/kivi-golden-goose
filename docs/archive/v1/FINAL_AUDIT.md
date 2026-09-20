# V1 audit preserved for historical reference

The following describes baseline 02868bc only. V2 validation is reported in eval/v2_report.md. V2 is not submission-ready until its live review path is verified.

# Final submission audit

Status: **SUBMISSION-READY** for the Golden Goose assignment requirements.

The repository has a complete normal-user product surface, real persistent backend, reproducible corpus/evaluation pipeline, migrations, source, tests, Part One documents, and explicit run/import/reset instructions. The model-backed path has also been exercised against a real provider. A free-tier quota prevented completion of the optional ten-case live semantic suite in one sitting; this is documented as a provider-limit caveat, not represented as a passing result.

## Verified in the packaged repository

- Normal-user web UI exposes Learn, Hey Kivi, Memory/control, and Why/trace flows.
- FastAPI backend, SQLite persistence, SQLAlchemy models, and Alembic migration are present.
- Python **3.12.x** is the documented validation runtime. Windows PowerShell instructions include a no-activation workaround.
- Provider configuration is vendor-agnostic: `KIVI_LLM_API_KEY` is canonical; `OPENAI_API_KEY` remains a compatibility fallback.
- Provider configuration fails fast when the model base URL is not an absolute `http://` or `https://` URL.
- Transient provider failures (`429/500/502/503/504` and transport failures) use bounded retry/backoff; permanent 4xx errors are not blindly retried.
- Manual real-model validation succeeded through Google's OpenAI-compatible Gemini endpoint: `Rajeev is my manager.` was interpreted as a high-confidence global relationship/current-state memory and admitted as `create`.
- The ten-case live semantic suite was additionally started against Gemini and progressed through multiple semantic cases before Google's free tier returned HTTP 429. No 10/10 result is claimed or fabricated.
- `python -m pytest -q`: **19/19 tests passed** in the final package.
- Fresh database migration succeeds from an empty state.
- Development corpus regenerates to **500 transcript-like records**.
- Offline regression processes **500/500 records** with **500/500 labeled admission checks passed**, **6/6 retrieval/grounding checks passed**, and **0 pipeline errors**.
- Missing/unknown Style path is exercised by **93 records**.
- Checked-in offline evaluation is explicitly labeled a deterministic regression baseline, not LLM-quality evidence.
- Credential-like content is blocked by deterministic policy.
- Active semantic memories retain provenance.
- README, RUN.md, Product Positioning, Product Vision, architecture/design/evaluation docs, corpus, generated offline results, migrations, source, and tests are included.
- The final archive excludes `.env`, `.venv`, caches, SQLite databases, and credentials.

## Evaluation distinction

`eval/results.json` is the checked-in **offline regression** artifact. It validates deterministic lifecycle, admission policy, persistence, provenance, retrieval plumbing, correction/deletion behavior, and grounding boundaries over the full 500-record corpus.

`eval/run_live_semantic_suite.py` exercises the configured real model path on ten deliberately difficult semantic cases. It is provided for reproducible semantic validation when provider quota is available. A large paid-model run is not required by the assignment and is not falsely implied by this repository.

## Remaining actions outside the codebase

1. Optional: let a reviewer (Aaditya) sanity-check this exact repository.
2. Push this exact repository to GitHub.
3. Run the documented clean-start commands once from the GitHub clone if time permits.
4. Record the exact final commit SHA.
5. Submit the GitHub URL + exact SHA; add a hosted URL only if one is intentionally provided.
