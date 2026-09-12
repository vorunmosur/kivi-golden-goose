# Evaluation strategy

The candidate evaluation should test the product contract, not only model quality.

## Corpus composition

Approximately 500 transcript-like records with raw ASR, LLM-formatted output, timestamp and ordinary metadata. The corpus must include:

- explicit facts and relationships;
- scoped and global preferences;
- projects and episodes;
- corrections and temporal changes;
- distributed information that requires combining multiple records;
- irrelevant chatter that should be ignored;
- weak inference that should clarify/abstain;
- credentials/secrets that must be rejected;
- missing/unknown Style metadata to verify generic behavior;
- contradictory and stale statements;
- temporary information where expiry is appropriate.

## Metrics / assertions

1. **Admission correctness**: save vs ignore/reject/clarify on labeled cases.
2. **Secret safety**: zero persisted credentials from labeled secret cases.
3. **Current-state correctness**: after corrections, exactly one active state for a semantic key.
4. **Provenance coverage**: every active memory has at least one source interaction.
5. **Retrieval hit rate**: expected supporting memory appears in top-k for grounded questions.
6. **Grounded QA**: answer supported by retrieved memory/source evidence.
7. **Abstention**: unsupported questions explicitly refuse to invent.
8. **Generic path**: records with missing/unknown Style produce valid memory behavior.
9. **Operational metrics**: ingestion latency, retrieval latency, end-to-end latency, DB growth, model usage and estimated cost when available.

## Result artifact

For each evaluated case, results should expose original input, extracted candidate, admission action and reason, created/changed/rejected memory, provenance, retrieved memory, Hey Kivi behavior, latency and model usage. Aggregate numbers are useful but do not replace case-level inspectability.

`eval/run_eval.py` therefore emits per-record cases, labeled admission accuracy, six query checks (including distributed evidence and unsupported-answer refusal), guardrail assertions, database size, aggregate token usage, optional cost, and a `pipeline_errors` list. The offline run is a deterministic regression baseline. A run with `KIVI_LLM_API_KEY` (or the `OPENAI_API_KEY` compatibility fallback) exercises the actual model path and is expected to expose model failures rather than silently substituting fixture outputs.
