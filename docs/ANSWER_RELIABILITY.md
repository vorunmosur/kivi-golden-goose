# Answer reliability validation

This pass starts at `9f7905779786b758eabf542ddd68bf698718a076`. It changes answer evidence, minimal context selection, temporal checks, identity rendering and two narrowly demonstrated extraction/planning failures. SQLite, in-process embeddings, FastAPI and local Qwen/Ollama remain. No full 500-record ingestion or UI pass was performed.

## Results and execution boundaries

| Validation | Before | After |
|---|---:|---:|
| Frozen query checks | 39/44 | 42/44 |
| Existing adversarial checks | 11/12 | 12/12 |
| New targeted queries | — | 8/8 |
| Native correction checks | 37/42 | 41/42 |
| Native alias/identity checks | 17/18 | 18/18 |
| Automated tests | 83 | 120 |

Final frozen results combine all 19 earlier R2 checkpoint queries with all 25 final checkpoint queries. Adversarial results similarly combine five earlier queries with seven final queries. This is an affected recheck, not a single full replay at the last SHA. The final application commit is `f37ebb4f77a7a6db1b25b7126e2951b4cdf2573a`; its only change after the structured-draft version restores descriptive `uses_*` slots, affecting final-checkpoint drafts. Earlier checkpoint questions are unaffected. Per-run source hashes and heads are retained in code manifests. The full R2 frozen replay scored 39/44; the initial reliability replay scored 29/44. Neither failure set was replaced.

Native before/after runs each used 13 independently labelled scenarios and 60 checks. After captured head 882e225, with application source hashes matching b97223b at start. Later temporal and draft refinements were not a new native ingestion run. Native state code remained unchanged. All after current/history/provenance state checks passed; the remaining out-of-order historical answer abstained because its claim cited only the former holder rather than both timeline endpoints. The final prompt requests both endpoints, but improvement on this particular native scenario has not been measured and is not claimed.

The full automated suite passed **120 tests in 15.13 seconds**, with three deprecation warnings; see `eval/reliability-tool-slots-final-tests.txt`. No subsequent application change was made. Old submitted V1 and all previous releases remain preserved.

## What changed and why

- The model now chooses short pack-local evidence handles such as E1. Application code maps them to the actual supplied memories and source interactions. Unknown handles, incorrect preference references and unsupported claims fail closed. This reduces ID copying errors without weakening provenance. Traces retain original generation, handles, mapped claims and verification.
- Relative timing is checked against a reference time, source/event dates and explicit validity intervals. Reinforcement does not make an old episode happen today. Supported durable current facts and explicitly dated historical quotations remain usable. “Recently” uses seven days and “just completed” uses 24 hours; these are explicit bounded policies, not universal linguistic rules.
- Draft context selects requested facts and scoped preferences. Incidental episodes are excluded unless requested. A regression removed `uses_material` and `uses_irrigation_method`; failing-before tests and replay answers were retained, then the generic descriptive slots were restored.
- Returned drafts contain only evidence-linked claim sentences. Uncited free-form generated attachments or commitments are omitted; cited sentences still undergo deterministic checks and full semantic verification. This improves support but does not make a citation proof of the entire sentence.
- Same-name people carry entity qualifiers into the pack and must remain distinguishable in the response. Both targeted museum/cycling-club answers name two distinct Alexes.
- Native evidence showed “used to / now” extraction deleting history and changing global scope to work scope. The extraction instruction now preserves the old slot, scope and history. A separate active-alias lookup prevents the planner arbitrarily choosing one of two people called Kat. The independent native scenarios improved from 54/60 to 59/60.

## Category comparison

Frozen multi-memory checks improved **9/10 → 10/10**, scoped preference checks **1/3 → 3/3**. Historical remains **2/3**, current correction **2/3**. Current versus tentative 3/3, episodes 3/3, app/time 1/1, forget leakage 3/3, ambiguity 3/3, unsupported abstention 3/3, non-retention 3/3, expiry 3/3 and personal scope 3/3 remain unchanged. Exact category inventories are in `eval/answer-reliability-review/comparison.json`.

Both frozen scored failures concern Cedar at earlier checkpoints: the takeover was not admitted, so current retrieval returns Mira and the historical takeover question abstains. Later reinforcement confirms Tessa, explaining final-checkpoint correctness. No frozen state was repaired. Query success at the final checkpoint does not erase earlier ingestion failure.

## Independent whole-answer findings

All 64 selected returned responses were reviewed separately from literal checks and model verdicts, with mapped claims and supplied source excerpts preserved in `eval/answer-reliability-review/independent-review.json`. No out-of-pack evidence handles appeared. Correct reference mapping does **not** mean every cited assertion is supported.

Concrete remaining findings, indexed within the preserved final query files:

- Frozen 499 #16, Juniper detailed email: “optimize” ticketing, QR entry/verification, team ensuring smooth systems and coordinator overseeing all operations exceed the source statements. The same-model verifier accepted these cited additions. This is a grounding/generation failure despite a literal pass.
- Frozen #5 and #17 expand coordinator to “coordinating everything”; #5 adds keep-her-in-the-loop advice. #11 and #17 add deadline-monitoring advice. Core facts are supported but prose is unnecessarily broad.
- Frozen #20 renders current oak-panel use as future “will utilize”; this is temporal wording drift not covered by the bounded relative-time vocabulary.
- Adversarial #0 adds “for all assets” to TIFF use; #2 calls the Dublin Core standard equipment. These are qualifier/predicate drift despite matching required values.
- Adversarial #1 adds an unnecessary coordinator and strengthens a delivery date into “must deliver”; #4 infers team progress and does not convincingly demonstrate the requested detailed style.
- Targeted #2 repeats the warmer-tone preference as a sentence in the draft instead of applying it. Several work updates read as factual notes rather than polished ready-to-send emails. Preference retrieval/citation succeeded; application quality is not established by that score.

The two new dated investigation answers correctly use July 8, 2026. Both identity answers preserve museum and cycling-club distinctions. The targeted minimal tool/date cases avoid invented attachments and old episodes, but the preference repetition above remains visible. Personal-scope tests establish absence of forbidden scoped preferences, not ideal tone or prose quality.

## Limits and next decision

These improvements are meaningful but do not establish production reliability. Deterministic checks cover bounded English patterns; they are not a complete semantic proof. A same-model verifier can still approve unsupported additions inside a correctly cited claim. Native correction coverage is seven scenarios, not a rerun of the 500-record corpus. Checkpoint replay cannot measure final-code ingestion performance or repair missing admitted evidence. Earlier release fresh-clone reviewer checks are historical and are not claimed as a new final-commit reviewer run.

Basic UI polish can proceed independently, but the system is not ready to present detailed drafts as uniformly grounded. Another full ingestion would be useful to measure the narrowly fixed correction/alias admission behavior; it would not solve the demonstrated prose-support failures. Prioritize those known generation failures before spending hours on a final clean 500-record run. This pass stops here: no new ingestion, UI work or automatic hardening pass is started.
