# Semantic-memory design contract

This document is the behavioral contract for the Golden Goose implementation. It exists so that the product does not collapse into a collection of prompts.

## Core principle

**Content determines the candidate. Context modifies scope and retention judgment. Deterministic policy enforces hard boundaries.**

Kivi Styles/situations are a useful starting point because they provide evidence about what a statement probably means and how useful or sensitive it may be. They are not separate memory systems, and the pipeline must still work when style/app metadata is absent or unfamiliar.

## General pipeline

1. Ingest raw ASR, formatted output, timestamp and any ordinary metadata.
2. Use a language model to propose zero or more semantic-memory candidates.
3. Validate every candidate against a strict schema.
4. Apply deterministic invariants (secret rejection, hide-mode retention boundary, confidence floor).
5. Infer semantic scope from the content; source context is only a prior.
6. Reconcile against current state using subject + predicate + scope.
7. Create, reinforce, supersede, clarify, ignore or reject.
8. Store provenance for every accepted memory and an audit decision for every candidate.
9. Retrieve active, non-expired memory for Hey Kivi.
10. Answer only from retrieved memory/source evidence; abstain when unsupported.

## Why a hybrid LLM + code design

The LLM is good at interpreting unfinished natural language, recognizing relationships and preferences, and spotting corrections. It is not granted direct authority over durable state. Code owns invariants that must be stable across runs: credentials are never stored, low-confidence inference is not silently promoted, deletion/supersession has explicit semantics, and every write is auditable.

This boundary is deliberate: pure rules are too brittle for arbitrary user history; pure LLM memory writes are too inconsistent for a system that accumulates state over time.

## Styles/situations

- **Developer:** project/tool/workflow preferences can be useful. Credentials, tokens and one-off debug values are excluded.
- **Email:** communication/tone preferences can be useful. Financial/credential material is excluded.
- **Work messaging:** useful for roles, projects, deadlines and evolving work context; conversational chatter is usually not durable.
- **Personal messaging:** higher admission bar because transient and sensitive information are dense.
- **Other/unknown:** conservative generic policy. This path is first-class, not a fallback that loses capability.

A global fact remains global even if spoken in a context-specific app. “My manager is Priya” should not become `work:developer` merely because it was said in VS Code. Conversely, “I prefer concise emails” is email-scoped even if said in a generic note.

## Memory types

The implementation supports factual, preference, relationship, project and episodic memories. These are intentionally broad. `canonical_text` preserves arbitrary semantic content while `subject/predicate/value` provides structured reconciliation when a stable key exists.

## Corrections and state changes

A supported newer value for the same `subject + predicate + scope` supersedes the old active memory rather than deleting history. The old row remains inspectable as historical state with provenance and `valid_to`.

The system must not confuse a new relation with a correction. “Aaditya is reviewing my work” does not automatically overwrite “Rajeev is my manager.” If the relationship is unclear, the extractor should propose clarification instead of mutation.

## Generic-evaluation guarantee

The hidden evaluator may provide arbitrary dictations with only ordinary log metadata. Therefore:

- unknown/missing Style must not disable extraction;
- no semantic key is allowed to depend on a hard-coded demo entity;
- no query path assumes manager/project/email fields;
- retrieval operates over generic canonical memory text plus structured fields;
- unsupported questions must produce an abstention, not an invented answer.

## Dictation vs Hey Kivi

Semantic memory is not injected into ordinary dictation by default. Dictation remains a text-production path. Hey Kivi is where durable semantic understanding can legitimately influence answers and tools. This keeps memory useful without silently changing the user's literal speech.

## Single-valued vs multi-valued memory

Not every shared predicate is a replacement slot. The extractor marks candidates as `single` or `multi` cardinality and describes whether the new evidence is an assertion, addition, replacement or correction. Deterministic reconciliation only supersedes existing state for single-valued slots or explicit replace/correction events. This prevents a related fact such as “Aaditya reviews my work” from accidentally overwriting “Rajeev is my manager.”

## Durable semantic memory vs source history

Hey Kivi uses two evidence layers. Active semantic memory is the primary source for current durable state and preferences. Original interaction history is a secondary evidence layer for one-off episodes that were correctly *not* promoted to durable memory. This avoids the bad incentive to remember everything merely so future Q&A can work. When old source history conflicts with newer active memory, current active memory wins.

This also improves robustness to a generic evaluation corpus: a reasonable question about a one-off event can still be answered from source evidence, while durable memory remains selective.

## Forgetting

An explicit forget request is interpreted as a proposed deletion, but code performs the mutation. A unique target is marked deleted and removed from future retrieval. Zero matches produces no mutation; multiple plausible targets produce clarification instead of broad deletion.
