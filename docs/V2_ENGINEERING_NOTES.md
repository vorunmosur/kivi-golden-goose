# Engineering reasoning to understand and defend

## What a memory is
A transcript records a statement. A memory records an interpreted belief supported by that statement. The model can be accurate about the meaning of a possibility while the possibility remains uncertain. Extraction confidence and certainty answer different questions.

## Why deterministic reconciliation
An LLM interprets language well but must not control lifecycle invariants. Tentative/future beliefs coexist with current state. New confirmed evidence may close a previous current interval. Corrections preserve previous and new state. Exact-value repetitions add sources without duplicates. Older evidence becomes historical. Explicit forgetting installs a cutoff independent of whether any memory was promoted.

## Why entities and aliases
Names connect distributed facts. Aaditya reviews Golden Goose; Golden Goose uses FastAPI. A single relational hop retrieves the project facts while drafting to Aaditya. An alias needs explicit evidence. Same-name people from different contexts remain distinct. Unsupported role/type/uncertainty qualifiers must not create new identities for the same user.

## Why embeddings
An embedding represents semantic similarity, so login issue can find auth middleware and refreshed tokens. It proposes related candidates; it does not decide current truth. Exact cosine scan is adequate for this single-user corpus. Model tags prevent comparing vectors from different embedding models. Failures are visible as lexical fallback.

## Why SQLite
The main need is atomic beliefs, source links, changes and forget boundaries for one local user. SQLite supplies transactions, indexed relationships and a reproducible local review path. DuckDB is attractive for analytical evaluation, not necessary for primary mutable state. Postgres fits concurrent centralized users. A dedicated graph/vector service would add setup without solving a measured bottleneck here.

## How preferences stay conservative
Explicit preferences apply immediately in the stated scope. Single edits are observations. Inferred patterns require distinct sources across independent sessions/days and consistency. New contradictory behavior withdraws inferred personalization; explicit evidence dominates inference. A more specific matching scope wins. Thresholds are configurable policy baselines, not evidence of statistical calibration.

## What grounding does and does not prove
IDs must be supplied in context and tied to individual personal claims. A second Qwen call verifies the complete answer against original excerpts. It checks recorded-history support, not external objective truth. Missing/invalid/unsupported evidence abstains. This is an additional model check with correlated-error risk, not a formal proof.

## What live evaluation taught
Initial optional fields let Qwen omit the source span, so admission correctly ignored facts. Native extraction now requires the actor and essential evidence/lifecycle/entity fields; optional qualifiers and dates remain optional. A default user subject silently changed Aaditya into the user, so subject is now mandatory in validation too. Source app metadata had also contaminated preference scope; scope must come from the preference statement. Confirmation refreshes canonical text and vectors, otherwise a stale might statement can undermine grounded current answers. V1 blocked any token discussion, which also blocked useful authentication episodes; credential detection now targets disclosed values. The initial verifier confused user assertions with externally verified truth; it now explicitly accepts this same user's statements as evidence. These are real model/system failures, not fabricated passing results.

## Forgetting tradeoff
The system retains audit records for inspection while excluding forgotten facts from Hey Kivi. All older unpromoted full transcripts are conservatively excluded because paraphrases may evade token redaction. Unrelated structured facts can still use a safe supporting span; transcripts containing deleted memory clauses/values are withheld. This reduces some historical recall and must be described honestly. Stronger future systems could attach claim-level source spans to every searchable episode and re-index redacted evidence.

## Next evidence needed
Unknown-user 500-record live runs need independent semantic annotations, not labels produced by this extractor. Measure current-state accuracy, unsupported-claim rate, entity ambiguity, forgotten-fact resurrection, scoped preference precision, episodic Recall@k and latency. Save failure cases. Pilot success alone does not establish this generalization.

## Reviewable UI controls
Correction uses an inline input and forgetting creates an audited decision. Reset requires a second explicit page click. These controls avoid native browser dialogs and were exercised through Learn, Hey Kivi, Memory and Why. Citation IDs are limited to the original excerpts actually present after context truncation, not every historical provenance link.


## Repository review: reproduced failures and fixes
The delivered `f3b4423` snapshot had no substantive dirty tracked changes. A byte-level comparison found 48 CRLF/LF-only differences; the initial 45-test suite passed. V1 commit `02868bc` remains an ancestor, and its submission audit lives under `docs/archive/v1/`.

The fresh 16-record local Qwen pilot passed 8/9 query checks and 5/5 state checks, with no ingestion failures or missing provenance. The failed exhibition-organizer question exposed a fact whose named object became an entity only in a later interaction. Retrieval now resolves only exact, unique names or explicitly evidenced aliases for these unlinked objects; ambiguous names remain unlinked. Two regression tests passed.

Deletion was processed before confidence and verbatim-evidence validation. Two failing tests demonstrated deletion from a fabricated excerpt and from confidence 0.2. Validation now runs first; both cases leave memory and boundaries unchanged.

Four additional failing tests exposed alias forget targets, qualified subject over-deletion, merging qualified object homonyms, and qualified object over-deletion. Matching now includes resolved entity identity. Forget boundaries carry nullable subject/object IDs; migration 0003 preserves the conservative interpretation of legacy null-ID boundaries. Separate qualified sources remain usable, while shared sources containing a deleted clause remain suppressed. The affected 11 tests passed, and the full suite including fresh/existing-versioned/existing-unversioned V2 migration checks passed 56 tests with three dependency/API deprecation warnings. These are deterministic regressions, not model quality estimates.

The independent 500-record model-backed challenge is a separate evaluation, with frozen inputs and incremental failures retained. Its raw results and any independently justified scoring corrections must remain separate from code-fix replays. Optional null/default extraction fields can be omitted to reduce generated-token overhead; required evidence and lifecycle fields remain mandatory.


A supported steam-oven fact was rejected because Qwen copied an auxiliary entity excerpt from prior state. This failure is retained in the raw longitudinal ingestion log. Auxiliary entity evidence is now validated independently, discarded with audit reasons when unsupported, and never admitted as an alias. The assertion's own verbatim evidence/confidence gates remain unchanged. A failing-before/passing-after regression preserves the supported fact without inventing the copied alias.

Extraction previously supplied 40 recent active memories regardless of the source's subject. Measured prompt size grew above 4,000 tokens and prompt evaluation alone exceeded 15 seconds. The context now selects up to 24 exact subject/value/predicate or project/recipient-scope matches, with eight recent beliefs for implicit references. An old-project test after 44 unrelated projects proves relevance survives recency truncation. This is a bounded lexical context selector, not a claim of universal coreference resolution. Live replays measure the final effect.


Raw deadline candidates labelled a currently scheduled November due date as future truth, rather than a current belief whose value is a future date. The extractor guidance now distinguishes assertion validity from the date mentioned in the value; temporary intervals still retain explicit expiry. A client-only preference also copied a serialized prior scope and dropped its client restriction. Native Qwen extraction now requires a structured scope object with all four nullable fields, and prior structured scopes are decoded before presentation. This prevents arbitrary `project` strings and stringified JSON from silently replacing scope semantics. Explicit recipient restrictions remain model interpretations, tested by client/internal/personal evaluation rather than claimed infallible.


## Alias and forget support: repository review
Names merely co-occurring in a source were previously enough to certify an alias. A regression demonstrated Ari being treated as Atlas from "Ari reviews Atlas." New bindings now receive an explicit-binding evidence verdict from Qwen; offline cue checks exist only for deterministic tests. Failed binding metadata is removed without blocking the separately supported review fact. Usage and verdicts are retained in decisions and ingestion responses.

A forgotten alias previously remained usable through EntityAlias. Certificates are now inactive when a matching literal boundary/deleted binding covers their original source. Alias lookup filters them, canonical actor inference from an inactive alias is declined, and explicit binding relearning updates the certificate to the new source. The forget verifier can identify explicit certificate removals even if no alias memory was promoted. Entity inspection reports active aliases separately from historical certificate evidence. Audit data is retained; forgetting is retrieval exclusion.

Natural deletion requires actual source support for the target, not just a verbatim unrelated excerpt or high confidence. Qwen verifies the subject/slot/scope/member and any explicitly removed alias certificates. Offline tests require a forget cue; selected Memory controls use their trusted row IDs. A non-retention source always blocks new fact admission and raw search, while verified instructions to stop remembering an existing fact may delete it. Exclusion is committed before extraction so provider failure cannot make that source searchable.

The longitudinal baseline also exposed reciprocal Vera/VeraBee metadata under production's autoflush=False. The original unit fixture used automatic flushing and masked this failure. Fixtures now match production; accepted certificates explicitly flush before processing the next mention, and canonical self aliases are discarded. The production-matched suite then uncovered pending expiry changes being selected as current; expiry now flushes before eligibility queries. The full suite passed 69 tests with the same three deprecation warnings.

Alias-based grounded actor claims need both the action excerpt and the actual binding excerpt. A failing-before/passing-after source-pack regression covers these two disjoint spans. Hey Kivi appends only relevant active certificates whose excerpts pass the same forget-safety checks, and permits their original interaction IDs as supporting evidence. Canonical IDs and similar spellings alone are not identity proof.

The early confirmed-role baseline left Mira and Tessa simultaneously active for Cedar Archive, with different owner/predicate/scope keys. Stable single roles now use the entity whose role changes as slot owner and preserve predicate/scope across correction. General named-entity facts avoid redundant project scope. This interpreter guidance is model-dependent and must be judged by the independent replay, not the prompt wording.

Windows locale-dependent scratch edits also briefly corrupted curly-quote test expectations and the new harness's abstention string. Those failures are retained as tooling errors. Source/file operations now use UTF-8 explicitly and the harness's curly apostrophe is an ASCII Unicode escape. Fresh 69-test validation passed after repair; no scoring correction is concealed in the original baseline artifacts.


The independent native privacy probe exposed a deletion-path scope bug: Qwen proposed source metadata Notes/unknown for a global alias forget, and support validation correctly rejected it. Reconciliation computed a source-supported normalized scope but passed the original candidate to forget. Deletion now passes that same normalized scope; the failing-before regression passes, together with 17 related alias/forget tests. The original native failure remains in privacy-live; the corrected replay must independently verify certificate deactivation and no alias-based role leakage.


The corrected native alias-forget replay deactivated the certificate but still passed 13/14: Qwen inferred Dori=Dorian from stale canonical role text, despite the only safe excerpt naming Dorian. The verifier explicitly approved that unsupported binding. A deterministic guard now abstains for a forgotten alias without active or independent identity evidence and rejects such names in generated output even if the model verifier approves. Canonical context containing an inactive owned alias is rebuilt from the surviving triple; audit storage remains unchanged. Two failing-before regressions reproduce query inference and an overconfident verifier. Exact word matching preserves Dorian, and explicit binding relearning makes the alias usable again. An intermediate local-import error is retained in alias-leak-after.txt; alias-leak-fixed-tests.txt records the corrected targeted tests.


Two failing-before regressions also showed that an optional empty entity qualifier erased a validated core subject/object qualifier. Core identity now has priority; auxiliary mentions inherit it only when their own evidence contains that context, otherwise they are discarded without discarding the supported fact. Qualified fact objects resolve their identity even when optional metadata is discarded. This avoids merging museum/cycling homonyms through schema defaults.


A subsequent native replay omitted aliases from both entity mentions while returning a supported Dorian/alias/Dori relationship. Dori became a separate entity and the alias memory became an entity edge; later forgetting withheld even independent Dorian evidence through conservative substring masking. The 12/14 replay remains in privacy-final-live. Core alias assertions now recover missing optional binding metadata using their own verbatim evidence, then receive the existing binding verdict before admission. Identity assertions run before dependent name facts, and their primary mention runs first. The model candidate output remains unchanged in API results; recovered metadata and verdicts are audited in decisions. A role-first/reversed-mention regression preserves one canonical identity and a literal alias value. The English cue is only a proposal gate; actual model support still decides admission.
