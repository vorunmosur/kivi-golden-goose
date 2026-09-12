# Architecture decision record

## Product slice
Kivi learns selectively from the situations it already appears in—Developer, Email, Work Messaging, Personal Messaging and Other—and uses durable semantic understanding only when the user addresses Hey Kivi. The same sentence can therefore receive a different retention decision depending on context, sensitivity, explicitness, temporality and confidence.

## Why SQLite, not Postgres
SQLite is the primary review database because the assignment corpus is ~500 records, the reviewer must be able to clone and run the exact commit, and the hard engineering problem here is semantic truthfulness rather than distributed database scale. SQLite provides transactions, foreign keys, durable state, inspectability and a zero-service setup. It also makes database growth easy to measure. Postgres would be appropriate later for concurrent multi-user production, but adds Docker/service/network failure modes without improving this evaluation.

## Why no vector database
At this scale, embeddings are stored directly on memory rows and cosine similarity is computed in-process. This makes the retrieval logic inspectable and avoids introducing a vector service solely for 500 records. The design can migrate to pgvector/vector DB later without changing the memory lifecycle abstraction.

## Memory lifecycle
1. Interaction arrives with raw ASR, formatted text, app, Kivi Style/situation, session and timestamp.
2. Context policy defines the prior: Developer strongly excludes secrets; Personal Messaging uses a higher admission bar; Email can learn durable communication preferences; Work Messaging is useful for evolving work facts and episodes.
3. LLM extracts candidate semantic memories and explicitly proposes create/update/clarify/ignore/reject.
4. Deterministic guardrails enforce secret rejection, Hide Mode, confidence threshold and semantic-key update behavior.
5. Accepted memories are stored with type, subject, predicate, value, scope, confidence, source style and provenance.
6. New values for the same single-valued subject/predicate/scope supersede the old active state while preserving history. Multi-valued knowledge coexists, and out-of-order older evidence cannot replace newer state.
7. Hey Kivi performs hybrid retrieval over active, non-expired memories and answers only from retrieved evidence.
8. Every admission and query creates an inspectable trace.

Grounded generation has a second deterministic boundary: the model returns a structured answer plus the exact memory/interaction IDs it used. IDs outside the supplied evidence, an unsupported flag, or an answer without citations results in abstention. Deleted and superseded semantic sources cannot reappear through raw-history fallback; Hide Mode and credential-like interactions are excluded from history retrieval entirely.

## Defensible boundary: Dictation vs Hey Kivi
Ordinary dictation is preserved as the user's text-production path. Semantic memory does not silently rewrite it. Semantic memory is applied in Hey Kivi because that is where a request can legitimately depend on durable facts, preferences and episodes. This follows the Golden Goose brief and avoids memory unexpectedly changing literal dictation.

## Deliberate simplifications
- Single-user local product.
- No ASR: transcript replay is the input boundary permitted by the brief.
- No Gmail/Calendar integration: the demo proves memory and grounded use rather than broad tool coverage.
- Hide Mode is implemented as a small extension because it directly exercises a retention boundary, but it is not the core use case.
- Model-provider layer is replaceable. Full evaluation expects an LLM key; deterministic demo mode exists only to let the UI run without one.
