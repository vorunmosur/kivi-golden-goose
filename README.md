# Kivi Golden Goose — Contextual Semantic Memory

A working end-to-end semantic-memory demonstration for Kivi. The product starts from Kivi's existing Styles/situations rather than a generic memory inbox: Developer, Email, Work Messaging, Personal Messaging and Other provide context for what deserves to become durable understanding.

## Thesis
Kivi should be selective, not a lifelog. The system treats `see`, `remember`, and `use` as different decisions. It learns durable facts/preferences/projects/episodes when they will reduce future user effort; it rejects secrets, does not promote weak inference into fact, supersedes stale state, preserves provenance, and applies semantic memory primarily in Hey Kivi rather than silently rewriting ordinary dictation.

## Core use case
Across ordinary work, Kivi learns a person's evolving work world: relationships, current projects, preferences and time-bounded episodes. In a fresh Hey Kivi session the user can ask a question or request a draft without rebuilding that context. Answers show which memories and source interactions produced them, and unsupported questions are refused rather than invented.

## Architecture
FastAPI + SQLAlchemy + SQLite, served as a single local process. LLM extraction and answering are isolated behind a provider-agnostic OpenAI-compatible layer with bounded retry/backoff for transient 429/5xx/transport failures. Embeddings are stored on memory rows; at this corpus size cosine similarity runs in-process. Styles are context signals, not partitions: missing/unknown metadata still follows the same generic memory pipeline. Hey Kivi retrieves active semantic memory first and may use original interaction history as secondary evidence for one-off episodes that should not become durable memory. See `docs/ARCHITECTURE.md` and `docs/DESIGN_CONTRACT.md` for the rationale.

## Context-aware admission
- **Developer:** learn durable project/tool/workflow preferences; reject secrets/credentials and one-off debug values.
- **Email:** learn durable communication preferences and relationships; reject financial/credential data.
- **Work Messaging:** learn evolving work facts, project context, relationships and meaningful episodes; ignore transient chatter.
- **Personal Messaging:** higher retention bar; explicit requests/corrections matter most.
- **Other:** conservative generic policy.

## Memory types
Facts, preferences, relationships, projects and episodes share one extensible representation: subject + predicate + value + canonical text + scope + status + confidence + sensitivity + temporal fields + provenance. Candidate extraction additionally distinguishes single-valued state from multi-valued knowledge so a true correction can supersede stale state without collapsing unrelated facts.

## User control
The Memory surface exposes what Kivi retains and its source interactions; entries can be deleted. The Why? surface exposes admission decisions and query traces without making the user operate a developer console.

## Evaluation
The repository includes a reproducible ~500-record synthetic corpus generator and complete-pipeline evaluation. Every run leaves memory decisions and query traces inspectable, including latency/model-usage fields. Failures are intentionally not hidden.

The checked-in offline result processes 500 labeled records, including 93 with missing/unknown Style, and passes 500/500 admission expectations plus 6/6 retrieval/grounding checks. It persists no credential-like memory and every active memory has provenance. This is a deterministic regression baseline, not a claim about LLM quality. Run the same evaluator with `KIVI_LLM_API_KEY` (or the `OPENAI_API_KEY` compatibility fallback) to measure the model-backed extractor and grounded answerer; per-case errors remain visible in `pipeline_errors` and failed cases. A smaller `eval/run_live_semantic_suite.py` is included for low-cost semantic validation before a full 500-record live run.

Model responses use strict JSON Schemas for both candidate extraction and grounded answers. The answerer must return evidence IDs from the supplied context; unsupported, empty, or invalidly cited answers become an explicit refusal. Raw history excludes Hide Mode, credentials, and interactions whose semantic memory was corrected, superseded, or deleted.

## Limitations
This is a narrow assignment build, not production Kivi. It does not implement ASR, connected apps, multi-user auth, a distributed vector database, or full computer-use tooling. Permissioned connected-app actions belong to the product vision but would broaden the implementation beyond the smallest trustworthy semantic-memory slice.

The synthetic labels are intentionally coarse because several statements can reasonably be either clarified or retained depending on the model's interpretation. The offline extractor exists for reproducible lifecycle testing and supports a limited set of patterns. The model-backed evaluation is the meaningful measure of semantic generalization.

## AI use
AI may be used in Part Two for code, dataset generation and implementation. All consequential product/architecture decisions are documented so they can be defended independently of the coding tool.

The final manual live smoke path was exercised end-to-end with Gemini through Google's OpenAI-compatible endpoint: a natural-language manager statement was extracted as a global relationship memory and deterministically admitted. The included ten-case live semantic suite also progressed through multiple real-model cases before Google's free-tier quota returned HTTP 429; no full-suite pass is claimed. See `RUN.md` for exact reproduction instructions.
