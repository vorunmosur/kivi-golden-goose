# Kivi Golden Goose — Evidence-Backed Personal Memory

Kivi should not remember everything a user says. It should build a selective, evolving understanding of the person behind the interactions — and be able to show why it believes what it believes.

This repository implements that memory layer end to end.

It learns durable facts, relationships, projects, episodes and behavioral preferences from longitudinal interaction history; reconciles corrections and changing state; retrieves relevant context using structured and semantic signals; and uses that context in Hey Kivi without inventing unsupported personal knowledge.

The implementation runs locally with **Qwen3.5 9B + nomic-embed-text + SQLite**. No paid model API is required.

> **Reviewer:** start with [RUN.md](RUN.md).
> The fastest useful path is to run the application, teach Kivi a few evolving facts, query them through Hey Kivi, and inspect Memory / Why?.

---

## Product thesis

A useful personal assistant needs more than transcript search.

Over time, a user may say:

- “Rajeev is my manager.”
- “Priya might become my manager next month.”
- “Priya officially took over today.”
- “Keep my work updates concise.”
- “Golden Goose is due Friday.”
- “Correction — it moved to Saturday.”

Treating these as independent text chunks leaves the assistant with contradictory history.

Kivi instead separates:

**see → interpret → decide whether to remember → reconcile → retrieve → use**

The system maintains current state while preserving the evidence and history that produced it.

Three principles guide the implementation:

1. **See ≠ remember ≠ use.** Access to an interaction does not automatically make it durable memory or appropriate answer context.
2. **LLMs interpret semantics; deterministic code owns invariants.** Qwen interprets fuzzy language and proposes structured meaning. Code owns deletion, lifecycle transitions, confidence rules, temporal normalization, provenance and grounded-answer enforcement.
3. **Personalization must remain inspectable.** Memories, decisions, source evidence and query traces are visible rather than hidden behind a generated biography.

---

## What is implemented

### Longitudinal memory

Interactions can become:

- facts
- relationships
- preferences
- projects / project facts
- episodes

Memories use a generic structured representation built around subject, predicate and value, with scope, certainty, temporal state, lifecycle status and source evidence.

The schema is not tied to a fixed list of professions, people, projects or tools.

### Memory lifecycle

Kivi distinguishes new knowledge from changes to existing knowledge.

The reconciliation layer supports behavior including:

- create
- reinforce
- update
- supersede
- historical state
- tentative / future state
- ignore
- clarify
- delete / forget
- expire

For example, a confirmed manager change supersedes the old current manager without destroying the historical evidence that the old relationship existed.

### Evidence and provenance

Every retained memory is linked back to the interaction evidence that produced it.

Hey Kivi operates on evidence handles rather than unrestricted personal-context prose. Grounded answers are checked against supplied evidence, and unsupported questions fail closed.

The UI exposes:

- **Memory** — what Kivi currently believes
- **Why?** — admission decisions and query traces
- source interactions and evidence
- correction / forgetting controls

### Hybrid retrieval

Retrieval combines multiple signals instead of relying on embedding similarity alone:

- semantic similarity
- structured predicates
- entity identity
- project anchoring
- relationship edges
- current vs historical state
- temporal constraints
- app constraints
- preference scope
- confidence / certainty
- lexical relevance

This supports both direct questions and information distributed across interactions.

For example, Kivi can combine a project's corrected deadline with its separately learned backend technology while preventing facts from an unrelated project from leaking into the answer.

### Scoped behavioral preferences

Explicit preferences can be learned immediately.

Behavioral preferences inferred from repeated behavior require stronger evidence and remain scoped unless evidence supports broader use. A narrow applicable preference can override a general one without rewriting the underlying factual answer.

Preferences affect presentation; they do not authorize fabrication of additional facts.

### Temporal and episodic retrieval

Hey Kivi can retrieve historical interactions using source-time and application constraints.

Explicit relative expressions such as:

> “Find the dictation around 5 PM yesterday in Slack”

are normalized deterministically against the supplied reference clock rather than trusting arbitrary model-generated time bounds.

### Forgetting and privacy boundaries

Hide Mode prevents retention.

Forget/delete creates a retrieval boundary so forgotten structured memory cannot silently re-enter through old raw-history evidence. New explicit evidence after the boundary may teach the information again.

Credential-like secrets are rejected from durable semantic memory.

---

## Architecture

```text
Interaction
raw ASR + formatted text + app/style + timestamp
        |
        v
Semantic interpretation — Qwen3.5 9B
        |
        v
Candidate memories
facts / relationships / preferences / episodes
        |
        v
Deterministic admission + lifecycle policy
        |
        v
Evidence-backed memory ledger
        |
        +---------------------------+
        |                           |
        v                           v
Structured/entity state       nomic embeddings
        |                           |
        +-------------+-------------+
                      |
                      v
              Hybrid retrieval
                      |
                      v
             Evidence context pack
                      |
                      v
        Grounded Hey Kivi realization
                      |
                      v
        support + contamination checks
```

### Stack

- Python 3.12
- FastAPI
- SQLAlchemy
- SQLite
- Alembic
- Ollama
- Qwen3.5 9B
- nomic-embed-text
- pytest

SQLite is intentional for this assignment: the product is a local, single-user memory system operating on hundreds of records. It provides transactional structured state, provenance and relational edges without requiring another service.

At larger multi-user scale, PostgreSQL and dedicated vector infrastructure may become appropriate. A separate graph database should be introduced only if measured traversal requirements justify the additional operational complexity.

---

## Reviewer surfaces

The local application exposes four primary product surfaces:

**Learn**
Submit an interaction or import longitudinal history.

**Hey Kivi**
Ask grounded questions or request constrained drafts using learned context.

**Memory**
Inspect retained state, evidence, lifecycle and corrections.

**Why?**
Inspect admission decisions and query traces.

The implementation is intentionally inspectable so evaluation does not depend only on whether a generated sentence sounds plausible.

---

## Final validation

### Clean 500-record model-backed ingestion

A final clean run processed the full 500-record development corpus through the actual Qwen/Ollama ingestion pipeline.

| Measure | Result |
|---|---:|
| Records processed | 500 / 500 |
| Ingestion failures | 0 |
| Missing provenance | 0 |
| Retained synthetic secrets | 0 |
| Median ingestion latency | 46.297 s |
| p95 ingestion latency | 73.051 s |
| Local provider spend | $0* |

\* Local inference cost excludes hardware and electricity.

The clean run is preserved under:

`eval/final-hardening-clean-500/`

The checked-in compact evidence contains summary, decisions, memories, entities, queries and traces. Large runtime database/intermediate artifacts are intentionally not required for repository review.

The final corpus runner did not assign semantic correctness labels to every resulting state/query, so these numbers are **pipeline-integrity results, not a claim of 500/500 semantic accuracy**.

### Frozen-state semantic challenge

After the 500-record state was frozen, an 11-case semantic challenge tested current-state correction, semantic paraphrase, distributed project facts, relationships, preferences, unsupported private information and grounded drafting.

Post-hardening benchmark result:

**9 / 11 scored passes (81.8%)**

The same frozen memory state was used; no re-ingestion was performed.

Important interpretation:

- the distributed project-facts case now correctly combines a corrected deadline with separately learned backend technology;
- the grounded manager-update case now retains both requested supported facts;
- one remaining scored failure is conservative handling of a tentative preference: Kivi refuses to claim it is confirmed but does not yet explain the tentative evidence;
- the private-information case correctly abstains with no memory leakage, but the small benchmark's literal scorer treats the Unicode apostrophe in `don’t` differently from `don't`.

The pre-hardening and post-hardening results are both retained so the improvement is auditable rather than replacing the earlier result.

### Automated tests

Final verification:

- **162 non-migration tests passed**
- **3 migration tests passed**
- **165 total passing tests**
- **0 test failures**

The remaining warnings are dependency/API deprecation warnings and do not represent failed behavior.

---

## Evaluation philosophy

The repository contains several layers of evaluation because one number is insufficient for a memory system.

Tests cover:

- admission and lifecycle invariants
- correction and supersession
- preference scope
- entity / alias behavior
- temporal retrieval
- forgetting boundaries
- semantic retrieval
- contamination prevention
- evidence completeness
- grounded realization
- migrations
- API behavior

Earlier development checkpoints are retained in `docs/` and `eval/` for auditability. They should be read as historical engineering evidence, not as the final headline result.

The most important distinction is:

> **A retrieved answer is not considered correct merely because its words match an expected string. It must also be supported by the supplied evidence.**

---

## Key design decisions

### Why not store a generated biography?

A free-form biography becomes a second source of truth and is difficult to reconcile safely.

Kivi instead derives its understanding from structured, evidence-backed memories.

### Why not pure vector RAG?

Similarity alone does not know that an old manager is no longer current, that a preference applies only to email, or that two projects happen to use the same technology.

Semantic retrieval is therefore combined with structured lifecycle, scope, entity and temporal constraints.

### Why deterministic lifecycle rules?

LLMs are useful for interpreting ambiguous language but should not independently decide hard invariants such as whether forgotten information can reappear or whether historical state becomes current.

Those transitions are explicit code paths.

### Why fail closed?

Personal context is unusually easy to hallucinate convincingly.

If Kivi cannot support a personal claim with available evidence, abstaining is preferable to inventing a plausible answer.

---

## Limitations

This is an assignment-scale implementation, not production Kivi.

Current limitations include:

- one local user;
- no authentication;
- no live connected-app actions or sending;
- exact vector scan rather than a dedicated vector index;
- local-model latency is substantial on the tested laptop;
- inferred behavioral-preference thresholds require broader calibration;
- historical recall is intentionally conservative across forget boundaries;
- tentative evidence is not yet surfaced richly in confirmation-status answers;
- arbitrary deep multi-hop graph reasoning is not claimed;
- model verification is an additional guard, not a mathematical proof of correctness.

These are intentionally documented rather than hidden behind aggregate scores.

---

## Repository guide

- [`RUN.md`](RUN.md) — fastest reviewer path
- `app/` — application and memory implementation
- `alembic/` — database migrations
- `tests/` — behavioral and regression tests
- `eval/` — corpus/evaluation harnesses and preserved results
- `docs/V2_CONTRACT.md` — implementation contract and invariants
- `docs/GROUNDED_REALIZATION.md` — grounded-answer hardening history
- `docs/ANSWER_RELIABILITY.md` — answer reliability development
- `docs/RETRIEVAL_HARDENING.md` — retrieval-hardening development

---

## AI assistance

AI assistance was used for Part Two implementation, test generation, debugging and engineering documentation.

The product decisions, architecture, evaluation interpretation and known limitations are made explicit in the repository so they can be inspected and defended independently of the coding tool.
