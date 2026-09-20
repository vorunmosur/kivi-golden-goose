# Independent longitudinal challenge protocol

`eval/longitudinal_cases.py` fixes input text and expectations before inference.
It imports neither the extractor nor a model. Ten project worlds from archives,
gardens, festivals, science, clinics, workshops, marine surveys, kitchens,
libraries and animation each contribute fifty interleaved chronological records.
The data are synthetic templates, deliberately repeated across worlds; results
must not be described as natural-user accuracy or independent human annotation.

There are 500 inputs, 410 scored admission cases (190 retain, 220 reject), 90
inspection-only cases, 70 state checks and 44 question/task checks. Expectations
are literal facts, source record identities and lifecycle invariants; no expected
labels come from the extractor under evaluation. Flexible predicate wording is
allowed. Admission checks measure whether a source supports any memory, including
historical/pending memory, rather than confusing retention with current activation.

Checkpoints exercise tentative and confirmed coordinator changes, date corrections,
forgetting every date version, explicit relearning, behavioral preference origin,
scope and expiry. Questions cover current truth, history, episodic paraphrases,
explicit app/date constraints, aliases, same-name ambiguity, forgotten history,
absent budgets, excluded locker codes, expired access, project-scoped work/client
preferences, personal-context exclusion and distributed multi-memory drafts.
Secrets are synthetic and never real credentials. Source provenance is checked
for presence and exact containment in original input. Full tables are exported,
avoiding the inspection API's 100-row decision/trace limit.

Retrieval source recall counts independently expected input IDs represented in
candidate memories or returned history. It is a provenance-based proxy, not
semantic Recall@k over all valid memories. Repeated independent sources can make
this conservative. Literal answer-key coverage, forbidden values, abstention and
returned preference scopes are independent answer checks; they do not prove that
every free-form claim is correct. The application's Qwen verifier is part of the
system being tested, not the evaluator's answer key. Its correlated error risk
remains a limitation. Read actual answers and evidence alongside aggregate metrics.

Every run writes original inputs, frozen expectations, incremental ingestion and
queries, state checks, full tables and a summary with failure counts, category
scores, recall/hit rate, latency, chat token counts and DB/WAL/SHM bytes. Model API
spend is zero for local inference; hardware/electricity and embedding token usage
are excluded. Output directories are write-once and failed runs exit nonzero.
Use `--limit N` for an explicitly partial challenge, never a 500-record claim.


## Additional independent diagnostic annotations
During review, 90 source-specific checks were added for scheduled-date validity, explicit client restrictions, first-person episode ownership/type, explicit alias certificates, and qualified same-name collaborators. These rules are authored from the source facts without calling or importing the extractor. They are post hoc diagnostics for the frozen baseline, saved in a separate `semantic_diagnostics.json`; the original expected input keys and raw summary are not rewritten. The rules are fixed before code-fix replay. Admission snapshots are reconstructed from decision state; the collaborator identity check uses exported final IDs. Literal metadata checks still need human interpretation for valid alternative paraphrases. Retention-only admission scores do not establish semantic correctness.
