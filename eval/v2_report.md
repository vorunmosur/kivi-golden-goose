# V2 Evaluation Report

> **Final-release note (2026-09-21):** The sections below preserve earlier evaluation checkpoints and their original results. They are intentionally not rewritten after later hardening.
>
> The final release subsequently completed a clean, model-backed 500-record ingestion run using Qwen3.5 9B and nomic-embed-text: **500/500 records processed, 0 ingestion failures, 0 missing provenance, and 0 retained synthetic secrets**. This is pipeline-integrity evidence, not a claim of 500/500 semantic accuracy. Compact evidence is preserved in `final-hardening-clean-500/`.
>
> Query-side hardening was then evaluated without re-ingestion against a copy of that frozen 500-record state. The post-hardening semantic challenge scored **9/11 (81.8%)**. One remaining scored failure is conservative treatment of tentative preference evidence; the other is a literal scorer mismatch on the Unicode apostrophe in an otherwise correct unsupported-information abstention. See `post500-semantic-challenge-post-hardening/`.
>
> Final automated verification: **162 non-migration tests + 3 migration tests passed, 0 failures**.
>
> For the final reviewer path, use `../README.md` and `../RUN.md`.

---

## Historical checkpoint record
# Latest grounded realization pass

Final checkpoint replay: frozen 42/44, adversarial 12/12, targeted 8/8 and realization originals/paraphrases 20/20. The automated suite passed 150 tests. Independent review classified 161/162 claims supported; both inadequate answers are the preserved Cedar ingestion-state miss. See [GROUNDED_REALIZATION](../docs/GROUNDED_REALIZATION.md). No 500-record ingestion rerun was performed.

# Previous answer reliability pass

Checkpoint checks improved 39/44 to 42/44; existing adversarial 11/12 to 12/12; targeted 8/8; focused native checks 54/60 to 59/60; automated tests 120 passed. No full ingestion rerun. Scores do not certify whole-answer support: independent review identifies unsupported operational additions and preference-application defects. See [ANSWER_RELIABILITY](../docs/ANSWER_RELIABILITY.md) for execution boundaries, preserved regressions and next-step recommendation.

# V2 validation report

Latest retrieval-only follow-up: **39/44 frozen queries**, **11/12 additional cases**, **83 automated tests**. The earlier evaluation below remains immutable evidence for earlier code. Scoped-answer regression and independent grounding failures are detailed in [RETRIEVAL_HARDENING.md](../docs/RETRIEVAL_HARDENING.md). No additional full ingestion run.

Baseline submission: `02868bc10e735bda361d4f48d1300a569f85647b`. Separate branch: `v2/semantic-memory-foundation`. Original repository and user-authored Part One documents are preserved.

## Current repository review (supersedes historical pilot claims below)

The delivered snapshot was exactly HEAD `f3b442355b5035bb881ffe806580367ceebba820`. All 48 differing tracked-file byte comparisons were line-ending changes; no substantive dirty code/results were recoverable. The original V1 object `02868bc10e735bda361d4f48d1300a569f85647b` remains intact and an ancestor. See `snapshot-audit.json` and `docs/REPOSITORY_TRUTH.md`.

Current automated suite: **77 passed, three deprecation warnings**, 14.80 seconds (`post-longitudinal-full-tests.txt`). The corrected 16-record native pilot passed 9/9 questions and 5/5 states; the final separate native privacy probe passed 14/14. These small runs do not establish broad accuracy.

The **complete 500-record Qwen/Ollama evaluation** (`longitudinal-final/summary.json`) passed **407/410 admission, 56/70 state, 24/44 query and 85/90 additional semantic diagnostic checks**. Zero ingestion failures, missing provenance, invalid evidence spans or retained synthetic secrets. Source recall averaged 0.3913 and hit rate 0.6087. Median/p95 ingestion latency: 29.065/45.428 seconds; query: 33.130/59.036 seconds. Recorded chat usage: 621 calls, 1,189,606 prompt and 102,149 completion tokens. Database plus sidecars at measurement: 7,855,088 bytes. Local API spend is zero; hardware/electricity and embedding token usage are excluded.

The full run used application commit `5c502bd`; the interruption at 62 records was recovered with unchanged application source and an audited runner-only modification. Original observations remain preserved. Query-only replays on observed checkpoints with later fixes passed **28/44**, including current-versus-tentative **3/3** (baseline 1/3). These reuse the original ingested states; they are not a second full ingestion run. Each replay records its exact source hash and commit.

Remaining failures include historical answers, incomplete multi-memory drafts, coordinator state drift, missing alias certificates (7/10 diagnostic pass) and scheduled-date interpretation (38/40). A nominally passing scoped draft imported an unrelated project's TIFF requirement: literal answer checks and citation presence overstate actual support. The same-model support verifier is not independent ground truth. See `docs/V2_REVIEW_FAILURE_ANALYSIS.md` for preserved failure details, correction reassertions and limitations.

The earlier 169-record run remains explicitly partial and is superseded as the main benchmark by this completed run. Its raw states (14/40), separately corrected actor-orientation scoring (24/40), and failed questions remain available. SQLite was not the demonstrated bottleneck; failures concern interpretation and retrieval, and local model generation dominates latency.

Exact final-commit fresh-clone installation, tests and HTTP reviewer-path results are delivered outside the repository with the release, avoiding a circular commit reference.

## Historical delivered V2 evidence

The following pilot results came with the supplied ZIP. They describe earlier code and must not be presented as final-commit validation.

## Automated and application checks
45 tests pass. Coverage includes lifecycle ordering, tentative confirmation, historical intervals, aliases and identity collisions, forget/relearning and withheld-source citations, conservative inferred preferences, scope precedence, hybrid retrieval, generic CSV import with duplicate replay, and correction/deletion controls. Fresh migration and a populated V1 upgrade were checked: source links remained intact, legacy project memories became facts, deleted slots gained boundaries, and SQLite foreign-key checks were clean.

The four-tab UI was exercised in the in-app browser using a separate offline plumbing database: Learn, answer/Why, inline correction, forget/abstention and two-click reset. Offline UI checks are not claimed as model-quality evidence.

## Actual local model pilot
Qwen `qwen3.5:9b` through native Ollama structured chat; `nomic-embed-text` semantic vectors. No candidate injection. Independent longitudinal fixture of 16 dictations: 9/9 answer checks and 5/5 stored-state checks pass. Ingestion failures: 0; missing provenance: 0; secret/non-retention memories: 0.

Checks cover Rajeev surviving tentative Priya, confirmed replacement, whole-slot forget including history, subsequent Ananya learning, correct Aaditya/Aadi relationship, coexisting work-email/client preferences, distributed project/backend/deadline drafting, a semantically retrieved authentication episode, generic ceramics-exhibition facts and missing-evidence abstention.

Ingestion median: 17.24s; p95: 33.86s (16-sample lower-index percentile, including fast rejected inputs). Query median: 31.41s. The first ingest took 173.19s under severe host RAM pressure; this small pilot is not a production latency benchmark. SQLite plus WAL measured 1,178,136 bytes at summary time. Local model API cost is $0, excluding hardware and electricity. Individual traces retain token counts, model timing, retrieved IDs and verification reasons.

Inspect [summary](v2_contract_validation/summary.json), [stored-state checks](v2_contract_validation/state_checks.json), [answers and evidence](v2_contract_validation/queries.json), [decisions](v2_contract_validation/decisions.json) and [inputs](v2_contract_validation/inputs.jsonl). Final citation assembly was tightened after this pilot; automated withheld-source tests and a final-code live smoke check accompany it. Both final-code live checks pass (current Ananya and alias-based project draft); inspect final_code_smoke.json.

## Failures retained
The first complete live pilot passed only 1/9 answers. Its results remain in `v2_live_pilot`. Intermediate interrupted runs are retained with ingestion/query records, not presented as completed evaluations. Failures exposed omitted evidence, defaulted actors, contaminated preference scopes, alias-value normalization, stale tentative canonical text on confirmation, overly broad credential blocking, and a verifier demanding external proof of user assertions. These were repaired and the complete pilot rerun. The initial failure report's database-size metric omitted live WAL and is not used as a growth comparison.

## Limits and next evaluation
A full 500-record live corpus run has not been completed. The generic JSON/JSONL/CSV importer and evaluation command are available in RUN.md; unknown-corpus probe answers are unlabeled and must be independently assessed. Pilot assertions are behavioral checks, not independently annotated claim-level accuracy or Recall@k. Do not report them as broad semantic-memory generalization.

SQLite and exact cosine scans suit one local user and this workload. There is no multiuser authentication or centralized concurrency validation. The second Qwen verifier has correlated-error risk. Forget is a retrieval boundary with retained audit storage; conservative exclusion of older full transcripts sacrifices some episodic recall. Entity disambiguation and temporal extraction still depend on language-model interpretation and require broader adversarial evaluation.
