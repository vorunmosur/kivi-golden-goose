# Grounded answer realization pass

This pass starts from application commit `f37ebb4f77a7a6db1b25b7126e2951b4cdf2573a` and addresses unsupported prose found by the independent answer review. It does not change memory ingestion, database architecture, entity resolution, retrieval architecture or UI. It does not rerun the 500-record ingestion.

## Outcome

Final application commit: `1319557d912a19ea79faae81f9681e0cee93b608`.

| Suite | Result |
|---|---:|
| Frozen queries | 42/44 |
| Existing adversarial cases | 12/12 |
| Existing targeted cases | 8/8 |
| Realization originals and paraphrases | 20/20 |
| Automated tests | 150 passed, 3 warnings, 18.59 seconds |

The two frozen failures are the accepted Cedar ingestion miss: at checkpoint 99 the current answer returns stale Mira because the Tessa correction was not admitted; at checkpoint 149 the historical takeover question abstains. No frozen state or benchmark label was changed.

The independent review covers all 84 final answers. It classifies 162 personal claims: **161 supported, 0 partially supported and 1 unsupported**. The unsupported claim is the stale Cedar/Mira answer above. Request adequacy is 82/84; the second failure is the Cedar historical abstention. All 35 cases that retrieved a scoped preference applied it behaviorally. A scan for the documented expansion patterns found zero returned matches. Exact answer-by-answer evidence is in `eval/grounded-realization-final-audit/whole-answer-review.json`.

## Implementation

Drafting now has two layers. Retrieval supplies privacy-eligible evidence. `answer_realization.py` then converts each eligible personal fact into an immutable proposition containing subject, predicate, value, certainty, temporal state, scope and identity qualifiers. Confirmed current slots use fixed sentences. Non-current or non-confirmed slots use a dated source quotation rather than promotion to present truth.

Style controls presentation only. Warmth adds a greeting and thanks; detail uses an itemized update; concise uses compact joining; direct uses the factual default. Preferences are retained as evidence but are not emitted as claims. Equipment/date drafts exclude unrelated roles unless the user requests people.

The free-prose answer model is not called for grounded drafts. Pack-local citation mapping, deterministic temporal/identity/contamination checks and provenance remain. The model verifier still runs as a diagnostic, but it cannot veto a mechanically proven proposition or cause abstention when it times out. Freely generated non-draft answers continue to require its approval.

The query planner may suggest constraints, but an entity is now trusted only when its name occurs in the query or explicit context. This prevented a model-generated list of unrelated people from causing a false â€œWhich Felix?â€ clarification. Explicit requests to create a message, note, email, update, briefing, summary or to brief someone enter the constrained artifact path.

## Concrete before/after findings

| Previous finding | Before | Final behavior |
|---|---|---|
| Juniper detailed email | Invented optimization, entry/verification, operational oversight and smooth-running work | Itemized purpose, QR-code use, coordinator and recorded deadline only |
| Coordinator expansion | â€œCoordinating everythingâ€ and keep-in-loop advice | â€œThe coordinator of â€¦ is â€¦â€ |
| Deadline monitoring | â€œKeep an eye on the deadlineâ€ | â€œThe recorded deadline â€¦ is â€¦â€ |
| Oak-panel tense | Current use became â€œwill utilizeâ€ | â€œMaple Workshop uses oak panelsâ€ |
| TIFF qualifier | TIFF became â€œfor all assetsâ€ | â€œThe format for Cedar Archive is TIFFâ€ |
| Dublin Core predicate | Standard was called equipment | â€œBirch Library uses Dublin Coreâ€ without calling it equipment |
| Delivery modality | Recorded date became â€œmust deliverâ€ | Recorded deadline statement |
| Unnecessary coordinator | Tool/date briefing added Alma | Final tool/date briefing contains sonar and deadline only |
| Detailed preference | Added plausible operational detail | More structured presentation using only supported propositions |
| Warm preference | Preference was repeated as an instruction | Greeting and thanks; preference is not narrated |

The 10 original cases and 10 paraphrases all pass. Earlier false passes and failures remain preserved: the first replay exposed removal of material/standard slots; R1 exposed artifact-intent misclassification; R3 exposed the hallucinated Felix clarification and a free-answer â€œbriefâ€ path; R4 exposed a verifier timeout. Each was fixed only after a concrete failure.

## Execution boundaries

The exact final result is an affected replay assembled transparently:

- Earlier 19 frozen and 5 adversarial non-draft queries ran at `12276aa`; later changes only alter structured draft handling.
- Final-checkpoint 25 frozen, 7 adversarial, 8 targeted and 20 realization cases ran at `e4a0105` after the deterministic-verifier authority change.
- The sole Coral verifier-timeout case reran and passed at final application commit `1319557`.

All manifests and earlier outputs are retained. Literal scores and same-model verdicts are diagnostics, not the independent semantic classification.

## Remaining limitations and next stage

Fixed templates deliberately trade expressive freedom for factual safety. They cover observed generic slots and quote unknown/non-current propositions; they are not a universal natural-language generator. â€œDetailedâ€ means presenting all supported relevant propositions with structure, not inventing explanatory detail. The deterministic pathway depends on ingestion having created the correct structured proposition. The frozen Cedar misses demonstrate that correct realization cannot repair absent state.

Recommended next stage: **C. Final clean 500-record ingestion/evaluation.** Focused native correction tests previously improved state checks from 54/60 to 59/60, and this pass removed the demonstrated realization failures. A clean full run is now the appropriate way to measure whether ingestion plus final realization work together. This report does not start that run.
