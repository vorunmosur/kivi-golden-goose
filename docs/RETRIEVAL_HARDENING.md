# Hey Kivi retrieval hardening

Starting commit: `3f3f1cc43c4210e219d4618a0140b727550e59c4`. Tested application commit: `479f199943eebb5685070e60bc1d2b4df3a46934`. Separate commits preserve all earlier artifacts. No new 500-record ingestion, database service or UI work.

## Before and after

| Category | Before | After |
|---|---:|---:|
| app_time | 1/1 | 1/1 |
| current_correction | 2/3 | 2/3 |
| current_vs_tentative | 3/3 | 3/3 |
| entity_ambiguity | 3/3 | 3/3 |
| episode_paraphrase | 2/3 | 3/3 |
| expiry | 3/3 | 3/3 |
| forget_leakage | 3/3 | 3/3 |
| historical | 0/3 | 2/3 |
| multi_memory_draft | 0/10 | 9/10 |
| non_retention | 3/3 | 3/3 |
| personal_scope | 3/3 | 3/3 |
| scoped_preference | 2/3 | 1/3 |
| unsupported | 3/3 | 3/3 |

**Frozen replay: 28/44 → 39/44. Additional 12 cases: 9/12 → 11/12. Automated tests: 83 passed, three deprecation warnings (14.79 seconds).** Source recall is recorded separately in final-comparison.json. These are single model runs, not statistically established accuracy gains.

## Where evidence was lost

1. A project linked to the shared user entity. One-hop expansion then admitted the user’s other projects. Exact predicate bonuses filled the eight-record context with unrelated work_on facts. Requested equipment, dates and historical coordinators were crowded out. Project anchors now bound candidates before ranking; the shared user is not an expansion bridge.
2. Historical requests favored coordinated activity records over coordinator slots. Unrelated user episodes displaced actual superseded holders. Retrieval-only grammatical role equivalence, project bounds and a larger historical budget retain the relevant timeline without rewriting stored predicates.
3. Drafting needed several different slots, while one global top-K favored repetitive high-scoring facts. Anchored drafts reserve distinct slots and applicable preferences, then group evidence into current state, relationships, preferences, episodes and history. This improves coverage, but overinclusive episode context remains a source of unnecessary generated claims.
4. The planner sometimes fabricated now/now time bounds for an undated episode question. Explicit user context now takes precedence, and undated requests do not inherit model-invented time limits.
5. Tool comparison missed format versus uses. A query-aware tool slot family expands candidate recall only for equipment/tool questions; stored relationships and their direction remain unchanged.
6. Same-name collaborators were serialized without explicit qualifiers and generated as one person. Packs now include entity IDs and qualifiers. Many drafts correctly distinguish both Alex identities, but one personal draft remains ambiguous; prompt instructions are not a complete deterministic identity guarantee.
7. A deterministic guard rejects unsupported known foreign-project names and exclusive foreign values even if the verifier accepts them. The first guard falsely rejected the generic word user; the adversarial failure and corrected test are retained. The guard does not catch every novel or implicit contamination.
8. Old traces discarded the exact pack and rejected raw generation. Exact reconstruction is impossible for those older fields; the audit explicitly says so. New traces retain ranked IDs/scores, the supplied grouped pack, raw generated claims and verifier result.

## Remaining failures and regressions

The Cedar current-correction and historical failures originate in a rejected ingestion correction. Its frozen state still says Mira; retrieval cannot invent Tessa’s missing admitted takeover. We did not silently repair the checkpoint.

Scoped client-email checks regressed from 2/3 to 1/3 (additional scoped case: 1/1 to 0/1). The correct detailed preference reaches the pack. The failures are inconsistent generated citation IDs, not scope-filter leakage: Harbor cites out-of-pack memory 282 and omits claim memory 82 from declared IDs; Juniper omits claim memory 218. Citation enforcement correctly refuses these answers. This regression is not hidden by the overall score gain.

Saffron drafting retrieves the requested tool and date, but adds unnecessary issue-status claims that conflict with a later resolution episode. The verifier rejects the entire answer. Broader context needs more selective composition.

Independent review found unsupported today/this-week claims in several literal-passing drafts, unsupported promises/monitoring language, an invented attachment in an adversarial note, and remaining ambiguous same-name prose. The same-model verifier accepted some of these. Passing content checks must not be called full grounding accuracy. See round2-independent-review.json for individual cases.

Missing alias certificates and malformed admitted state remain ingestion limitations. No fuzzy alias merging or raw-history escape around forget boundaries was introduced. Frozen forget, ambiguity, unsupported, expiry, non-retention and personal-scope controls retained their original passing scores; the suite includes existing alias/forget/provenance regressions.

## Interview explanation

The useful question is: did the answer receive all and only the evidence needed for this task? The principal bug was a graph traversal through the shared user that mixed projects, followed by a small ranking budget that discarded needed facts. The fix constrains candidates first, expands relevant slots second, and composes a typed evidence pack with provenance. It improves answers using the existing SQLite and in-process embeddings. More infrastructure would not fix selection mistakes or inconsistent model citations.

## Decision on another ingestion run

**Do not rerun all 500 records yet.** First fix citation-contract reliability, suppress unrequested episode elaboration, and enforce relative-time/identity support more deterministically. Those can be tested cheaply on existing checkpoints. Separately evaluate rejected correction and alias admission on focused native cases. A later end-to-end ingestion run becomes worthwhile when those state-changing fixes are ready and query-only checks stop regressing.

## Evidence

- `eval/retrieval-hardening-audit/all-query-audit.json`: all44 original/replayed questions with matching-checkpoint memories, entities, aliases, source spans, plans, candidates, answers and verifier evidence.
- `eval/retrieval-hardening-audit/round2-independent-review.json`: failures missed by literal scoring.
- `eval/hardening-r2-frozen-*` and `eval/hardening-r2-adversarial-*`: final native results, source hashes and complete traces.
- `eval/hardening-adversarial-before-*`: the same additional labels run on original3f3f1cc application code. Initial before/after and intermediate failed tests remain committed.
- `eval/retrieval-hardening-round2-tests.txt`: full automated suite.
