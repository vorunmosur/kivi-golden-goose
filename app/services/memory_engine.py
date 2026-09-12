from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Interaction, Memory, MemoryDecision, MemorySource, utcnow
from app.services.context_policy import policy_for
from app.services.memory_contract import CandidateBatch, MemoryCandidate
from app.services.provider import provider


SENSITIVE_REGEXES = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}\b", re.I),
    re.compile(r"\b(?:api[_ -]?key|password|passcode|otp|cvv|private key|access token|refresh token|secret key)\b", re.I),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
]

GLOBAL_RELATION_PREDICATES = {"manager", "boss", "partner", "spouse", "email", "phone", "timezone", "location", "home_city", "current_city", "employer"}


def _looks_sensitive(text: str, never_store_patterns: tuple[str, ...]) -> bool:
    lower = text.lower()
    if any(p in lower for p in never_store_patterns):
        return True
    return any(rx.search(text) for rx in SENSITIVE_REGEXES)


def _normalize_scope(candidate: dict, policy_default: str) -> str:
    """Context is a hint, not a hard partition.

    Explicitly global relationships/facts should not become developer-scoped merely because the
    statement appeared in VS Code. Conversely, a preference that explicitly concerns email/code
    should keep that narrower scope.
    """
    supplied = str(candidate.get("scope") or "").strip().lower()
    predicate = str(candidate.get("predicate") or "").strip().lower()
    text = f"{candidate.get('canonical_text','')} {candidate.get('value','')}".lower()

    # Semantic meaning wins over source application/style. A global relationship remains global
    # even when mentioned in VS Code, while an explicitly email/code-scoped preference stays narrow.
    if predicate in GLOBAL_RELATION_PREDICATES:
        return "global"
    if any(x in text for x in ["email", "emails", "message tone", "signature"]):
        return "work:email"
    if any(x in text for x in ["code", "coding", "backend", "frontend", "framework", "python", "fastapi", "react"]):
        return "work:developer"
    if supplied and supplied not in {"context", "current", "unknown", "auto"}:
        return supplied
    return policy_default


def _fallback_candidates(text: str, style: str, scope: str) -> list[dict]:
    """Conservative offline extractor for smoke tests only."""
    candidates: list[dict] = []

    if _looks_sensitive(text, policy_for(style).never_store_patterns):
        return [{
            "memory_type": "fact", "subject": "user", "predicate": "sensitive_data",
            "value": "[redacted]", "canonical_text": "Sensitive credential-like data.",
            "scope": "global", "confidence": 1.0, "explicitness": "explicit",
            "temporal": "temporary", "sensitivity": "secret", "proposed_action": "reject",
            "cardinality": "multi", "change_kind": "assert", "reason": "credential pattern",
        }]

    forget = re.search(r"\b(?:forget|don't remember|do not remember) (?:that )?(.+)", text, re.I)
    if forget:
        value = forget.group(1).strip(" .")
        candidates.append({
            "memory_type": "fact", "subject": "user", "predicate": "explicit_memory",
            "value": value, "canonical_text": value, "scope": "auto", "confidence": 0.95,
            "explicitness": "explicit", "temporal": "durable", "sensitivity": "normal",
            "proposed_action": "delete", "cardinality": "multi", "change_kind": "remove",
            "reason": "explicit forget request",
        })
        return candidates

    patterns = [
        (r"\b([A-Z][A-Za-z .'-]+) is my manager", "relationship", "manager", "global", "single"),
        (r"\bmy manager (?:is|changed (?:from [^ ]+ )?to) ([A-Z][A-Za-z .'-]+)", "relationship", "manager", "global", "single"),
        (r"\bi(?:'m| am) working on ([A-Z][A-Za-z0-9 ._-]+)", "project", "current_project", "global", "single"),
        (r"\bi(?:'m| am) also contributing to the ([A-Z][A-Za-z0-9 ._-]+?) rollout", "project", "project_membership", "global", "multi"),
        (r"\bi prefer (.+)", "preference", "preference", "auto", "multi"),
        (r"\bi (?:usually|often|typically) (.+)", "preference", "behavior_pattern", "auto", "multi"),
        (r"\bremember (?:that )?(.+)", "fact", "explicit_memory", "auto", "multi"),
        (r"\b(?:the )?deadline for ([A-Z][A-Za-z0-9 ._-]+?) is ([A-Za-z0-9 ,:-]+)", "fact", "project_deadline", "global", "single"),
        (r"\bcorrection:?(?: the)? ([A-Z][A-Za-z0-9 ._-]+?) deadline (?:has )?moved to ([A-Za-z0-9 ,:-]+)", "fact", "project_deadline", "global", "single"),
        (r"\b([A-Z][A-Za-z0-9 ._-]+?) uses ([A-Za-z0-9 .+#_-]+) for the backend", "project", "backend_stack", "work:developer", "single"),
        (r"\bactually,? ([A-Z][A-Za-z .'-]+) is reviewing ([A-Z][A-Za-z0-9 ._-]+?) now", "relationship", "project_reviewer", "global", "single"),
        (r"\bmeet ([A-Z][A-Za-z .'-]+) at ([A-Za-z0-9 :]+ tomorrow)", "episode", "upcoming_meeting", "global", "multi"),
        (r"\bmy home city is ([A-Z][A-Za-z .'-]+)", "fact", "home_city", "global", "single"),
        (r"\b([A-Z][A-Za-z .'-]+) works in the ([A-Z][A-Za-z .'-]+) time zone", "fact", "timezone", "global", "single"),
    ]
    for pattern, mtype, predicate, suggested_scope, cardinality in patterns:
        m = re.search(pattern, text, re.I)
        if not m:
            continue
        groups = [g.strip(" .") for g in m.groups()]
        candidate_subject = "user"
        value = ": ".join(groups)
        if predicate == "project_deadline":
            candidate_subject, predicate, value = groups[0], "deadline", groups[1]
        elif predicate == "backend_stack":
            candidate_subject, value = groups[0], groups[1]
        elif predicate == "project_reviewer":
            candidate_subject, predicate, value = groups[1], "reviewer", groups[0]
        elif predicate == "timezone":
            candidate_subject, value = groups[0], groups[1]
        is_correction = bool(re.search(r"\b(changed|correction|actually|now)\b", text, re.I))
        is_temporary = predicate == "upcoming_meeting"
        is_inferred_pattern = predicate == "behavior_pattern" or (predicate == "preference" and bool(re.search(r"\b(?:usually|often|typically)\b", text, re.I)))
        candidates.append({
            "memory_type": mtype,
            "subject": candidate_subject,
            "predicate": predicate,
            "value": value,
            "canonical_text": f"{predicate.replace('_', ' ')}: {value}",
            "scope": suggested_scope,
            "confidence": 0.95,
            "explicitness": "inferred" if is_inferred_pattern else "explicit",
            "temporal": "temporary" if is_temporary else "durable",
            "sensitivity": "normal",
            "proposed_action": "clarify" if is_inferred_pattern else "create_or_update",
            "cardinality": cardinality,
            "change_kind": "correct" if is_correction else "assert",
            "reason": "deterministic smoke-test extraction",
            "expiry_days": 2 if is_temporary else None,
        })
    return candidates

def _validate_candidates(raw: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, invalid = [], []
    for item in raw:
        try:
            valid.append(MemoryCandidate.model_validate(item).model_dump(mode="json"))
        except ValidationError as exc:
            invalid.append({"candidate": item, "error": exc.errors()})
    return valid, invalid


def extract_candidates(db: Session, interaction: Interaction) -> tuple[list[dict], dict, list[dict]]:
    policy = policy_for(interaction.style_context)
    text = interaction.formatted_text.strip()

    if provider.enabled:
        system = """You are Kivi's semantic-memory candidate extractor. You interpret language; you do NOT directly write durable memory.

GOAL
Extract only information that could make future Hey Kivi requests materially more useful. The system must work on generic records even when Style/app metadata is missing. Style/situation is supporting evidence for relevance, sensitivity, and scope; it must never be treated as a hard taxonomy.

WHAT MAY BECOME MEMORY
- factual understanding about the user or their world
- preferences / working style
- relationships / roles
- project context
- episodes that are likely to matter later

WHAT SHOULD NOT BECOME MEMORY
- filler, greetings, transient chatter, one-off wording
- credentials/secrets/private keys/OTP/payment-card data
- weak inference presented as fact
- temporary details with no future value

IMPORTANT RULES
1. Corrections and explicit changes are strong evidence. Use a stable predicate so deterministic reconciliation can supersede old current state.
2. Repetition is evidence, not proof. If a pattern is only inferred, set explicitness=inferred and proposed_action=clarify unless the evidence is unusually strong.
3. Context should scope only when the semantic content itself is scoped. Example: 'I prefer concise emails' -> email scope. 'My manager is Priya' remains global even if spoken in VS Code.
4. If there is no useful durable candidate, return an empty list.
5. For secrets use sensitivity=secret and proposed_action=reject.
6. For short-lived but useful episodes, use temporal=temporary and expiry_days when sensible.
7. Never fabricate a relation/key not supported by the interaction.
8. Normalize semantic slots around the entity they describe. Example: 'Golden Goose is due Friday'
   -> subject='Golden Goose', predicate='deadline', value='Friday'. Do not put the project name
   inside the predicate or collapse unrelated projects into one user-level deadline slot.
9. Consult current_active_memories only to resolve references and true changes. Never repeat an
   existing memory unless the new interaction supplies supporting evidence for it.

Return JSON only: {"candidates": [...]}.
Each candidate MUST contain these fields:
memory_type (fact|preference|relationship|project|episode), subject, predicate, value, canonical_text, scope,
confidence 0..1, explicitness (explicit|implied|inferred), temporal (durable|temporary|unknown),
sensitivity (normal|sensitive|secret), proposed_action (create_or_update|delete|clarify|ignore|reject),
cardinality (single|multi), change_kind (assert|replace|correct|add|remove), reason.
Optional: supersedes_predicate, expiry_days.

CARDINALITY / CHANGE RULES
- Use cardinality=single for one-current-value state such as current manager, current employer, primary project deadline.
- Use cardinality=multi for coexisting facts such as collaborators, tools used, project members, interests.
- A sentence explicitly saying "changed to", "now", "actually", "correction", or correcting an earlier value should use change_kind=replace/correct when it truly changes the same semantic slot.
- Do NOT mark a merely related fact as a replacement. "Aaditya reviews my work" must not replace "Rajeev is my manager".
- "Forget X", "don't remember X", or an explicit request to remove a known memory should use proposed_action=delete and change_kind=remove.
- If deletion target is ambiguous, use clarify instead of guessing."""
        # Give the interpreter a small view of current state. This makes references such as
        # "actually, move that deadline to Monday" resolvable without granting the model write
        # authority. Deterministic reconciliation below still owns the mutation.
        current = db.scalars(select(Memory).where(
            Memory.status == "active",
        ).order_by(Memory.updated_at.desc()).limit(40)).all()
        user = json.dumps({
            "raw_asr": interaction.raw_asr,
            "formatted_text": interaction.formatted_text,
            "style_context": interaction.style_context or "unknown",
            "app_context": interaction.app_context or "unknown",
            "occurred_at": interaction.occurred_at.isoformat(),
            "current_active_memories": [{
                "id": m.id,
                "subject": m.subject,
                "predicate": m.predicate,
                "value": m.value,
                "canonical_text": m.canonical_text,
                "scope": m.scope,
                "valid_from": m.valid_from.isoformat() if m.valid_from else None,
            } for m in current],
            "context_policy_hint": {
                "default_scope": policy.default_scope,
                "sensitivity_bias": policy.sensitivity_bias,
                "durable_signals": policy.durable_signals,
                "never_store_patterns": policy.never_store_patterns,
                "notes": policy.notes,
            },
        }, ensure_ascii=False)
        data, usage = provider.chat_json(
            system, user, CandidateBatch.model_json_schema(), "memory_candidates"
        )
        raw_candidates = data.get("candidates", []) if isinstance(data, dict) else []
        if not isinstance(raw_candidates, list):
            raw_candidates = [{"invalid_response": raw_candidates}]
        valid, invalid = _validate_candidates(raw_candidates)
        return valid, usage, invalid

    valid, invalid = _validate_candidates(_fallback_candidates(text, interaction.style_context, policy.default_scope))
    return valid, {}, invalid


def _record_decision(db: Session, interaction_id: int, candidate: dict, action: str, reason: str, memory_id: int | None = None) -> None:
    db.add(MemoryDecision(
        interaction_id=interaction_id,
        candidate_json=json.dumps(candidate, ensure_ascii=False),
        action=action,
        reason=reason,
        memory_id=memory_id,
    ))


def process_interaction(db: Session, interaction: Interaction) -> dict:
    policy = policy_for(interaction.style_context)
    candidates, usage, invalid = extract_candidates(db, interaction)
    actions: list[dict] = []

    for bad in invalid:
        _record_decision(db, interaction.id, bad, "reject", "Extractor candidate failed the strict memory-candidate contract.")
        actions.append({"action": "reject", "candidate": bad, "reason": "invalid candidate schema"})

    for c in candidates:
        candidate_text = f"{c.get('canonical_text','')} {c.get('value','')}"
        explicit_remember = bool(re.search(r"\bremember (?:this|that)?\b", interaction.formatted_text, re.I))

        # Hard invariants below are deterministic: model output cannot bypass them.
        if interaction.hide_mode and not explicit_remember:
            _record_decision(db, interaction.id, c, "temporary", "Hide Mode: usable in-session only; durable persistence is disabled unless explicitly overridden.")
            actions.append({"action": "temporary", "candidate": c, "reason": "hide_mode"})
            continue

        if _looks_sensitive(candidate_text + " " + interaction.formatted_text, policy.never_store_patterns) or c.get("sensitivity") == "secret":
            _record_decision(db, interaction.id, c, "reject", "Credential/secret guardrail blocked durable storage.")
            actions.append({"action": "reject", "candidate": c, "reason": "secret_guardrail"})
            continue

        proposed = c.get("proposed_action", "ignore")
        confidence = float(c.get("confidence", 0.0))

        if c.get("sensitivity") == "sensitive" and not explicit_remember and proposed != "delete":
            _record_decision(db, interaction.id, c, "clarify", "Sensitive information requires an explicit remember request before durable storage.")
            actions.append({"action": "clarify", "candidate": c, "reason": "sensitive_requires_consent"})
            continue

        if policy.name == "personal messaging" and c.get("explicitness") != "explicit" and proposed == "create_or_update":
            _record_decision(db, interaction.id, c, "clarify", "Personal-message context requires explicit evidence before durable storage.")
            actions.append({"action": "clarify", "candidate": c, "reason": "personal_context_high_bar"})
            continue

        if proposed == "delete":
            subject = c.get("subject") or "user"
            predicate = c.get("supersedes_predicate") or c.get("predicate") or "context"
            scope = _normalize_scope(c, policy.default_scope)
            value = str(c.get("value", "")).strip().lower()
            candidates_to_delete = db.scalars(select(Memory).where(
                Memory.subject == subject,
                Memory.status == "active",
            )).all()
            generic_delete_predicates = {"explicit_memory", "memory", "context", "fact"}
            def match_tokens(text: str) -> set[str]:
                tokens = set()
                for token in re.findall(r"[a-z0-9]+", text.lower()):
                    if len(token) <= 2:
                        continue
                    tokens.add(token[:-1] if token.endswith("s") and len(token) > 4 else token)
                return tokens

            target_tokens = match_tokens(value)
            predicate_pool = [m for m in candidates_to_delete if m.predicate == predicate]
            matches = []
            for m in candidates_to_delete:
                haystack = f"{m.predicate} {m.value} {m.canonical_text}".lower()
                overlap = len(target_tokens & match_tokens(haystack))
                text_match = bool(value) and (value in haystack or overlap >= max(1, min(2, len(target_tokens))))
                if predicate not in generic_delete_predicates:
                    semantic_match = m.predicate == predicate and (len(predicate_pool) == 1 or text_match)
                else:
                    semantic_match = text_match
                scope_match = scope == "global" or m.scope == scope or c.get("scope") in {"auto", "unknown", "context", None}
                if semantic_match and scope_match:
                    matches.append(m)
            if len(matches) == 1:
                target = matches[0]
                target.status = "deleted"
                target.valid_to = interaction.occurred_at
                _record_decision(db, interaction.id, c, "delete", f"Explicit forget request removed active memory {target.id}.", target.id)
                actions.append({"action": "delete", "memory_id": target.id, "reason": "explicit_forget"})
            elif len(matches) == 0:
                _record_decision(db, interaction.id, c, "ignore", "Forget request did not match an active memory; nothing was removed.")
                actions.append({"action": "ignore", "candidate": c, "reason": "no_delete_match"})
            else:
                _record_decision(db, interaction.id, c, "clarify", "Forget request matched multiple memories; Kivi should ask which one to remove.")
                actions.append({"action": "clarify", "candidate": c, "reason": "ambiguous_delete", "matches": [m.id for m in matches]})
            continue
        if proposed == "clarify" or c.get("explicitness") == "inferred" or (confidence < 0.72 and c.get("explicitness") != "explicit"):
            _record_decision(db, interaction.id, c, "clarify", "Evidence is too weak to promote into durable memory without confirmation.")
            actions.append({"action": "clarify", "candidate": c, "reason": "insufficient_evidence"})
            continue
        if proposed in {"ignore", "reject"}:
            _record_decision(db, interaction.id, c, proposed, c.get("reason", "Extractor recommended no durable memory."))
            actions.append({"action": proposed, "candidate": c, "reason": c.get("reason")})
            continue

        subject = c.get("subject") or "user"
        predicate = c.get("supersedes_predicate") or c.get("predicate") or "context"
        scope = _normalize_scope(c, policy.default_scope)
        value = str(c.get("value", "")).strip()

        same_slot = db.scalars(select(Memory).where(
            Memory.subject == subject,
            Memory.predicate == predicate,
            Memory.scope == scope,
            Memory.status == "active",
        ).order_by(Memory.updated_at.desc())).all()
        same_value = next((m for m in same_slot if m.value.strip().lower() == value.lower()), None)
        cardinality = c.get("cardinality", "multi")
        change_kind = c.get("change_kind", "assert")
        # Only single-valued state, or an explicit replace/correction, is allowed to supersede.
        existing = same_value or (same_slot[0] if same_slot and (cardinality == "single" or change_kind in {"replace", "correct"}) else None)

        # Replaying an older corpus must not make stale evidence current merely because it was
        # ingested later. Keep the existing current state and retain an auditable decision.
        if existing and existing.value.strip().lower() != value.lower() and existing.valid_from and interaction.occurred_at < existing.valid_from:
            _record_decision(db, interaction.id, c, "ignore", f"Older evidence cannot supersede current memory {existing.id}.", existing.id)
            actions.append({"action": "ignore", "memory_id": existing.id, "reason": "stale_out_of_order_evidence"})
            continue

        expires_at = None
        if c.get("temporal") == "temporary":
            days = int(c.get("expiry_days") or 7)
            expires_at = interaction.occurred_at + timedelta(days=max(1, min(days, 3650)))

        if existing and existing.value.strip().lower() != value.lower():
            old_id = existing.id
            existing.status = "superseded"
            existing.valid_to = interaction.occurred_at
            new_mem = Memory(
                memory_type=c.get("memory_type", "fact"),
                subject=subject,
                predicate=predicate,
                value=value,
                canonical_text=c.get("canonical_text") or f"{predicate}: {value}",
                scope=scope,
                confidence=confidence,
                sensitivity=c.get("sensitivity", "normal"),
                source_style=interaction.style_context or "other",
                explicitness=c.get("explicitness", "implied"),
                valid_from=interaction.occurred_at,
                expires_at=expires_at,
            )
            db.add(new_mem)
            db.flush()
            db.add(MemorySource(memory_id=new_mem.id, interaction_id=interaction.id, evidence_text=interaction.formatted_text))
            _record_decision(db, interaction.id, c, "update", f"Superseded active memory {old_id}: same subject/predicate/scope received a newer supported value.", new_mem.id)
            actions.append({"action": "update", "memory_id": new_mem.id, "superseded": old_id, "scope": scope})
        elif existing:
            existing.updated_at = utcnow()
            existing.confidence = max(existing.confidence, confidence)
            db.add(MemorySource(memory_id=existing.id, interaction_id=interaction.id, evidence_text=interaction.formatted_text))
            _record_decision(db, interaction.id, c, "reinforce", "Existing active memory matched; confidence/provenance were reinforced.", existing.id)
            actions.append({"action": "reinforce", "memory_id": existing.id, "scope": scope})
        else:
            mem = Memory(
                memory_type=c.get("memory_type", "fact"),
                subject=subject,
                predicate=predicate,
                value=value,
                canonical_text=c.get("canonical_text") or f"{predicate}: {value}",
                scope=scope,
                confidence=confidence,
                sensitivity=c.get("sensitivity", "normal"),
                source_style=interaction.style_context or "other",
                explicitness=c.get("explicitness", "implied"),
                valid_from=interaction.occurred_at,
                expires_at=expires_at,
            )
            db.add(mem)
            db.flush()
            db.add(MemorySource(memory_id=mem.id, interaction_id=interaction.id, evidence_text=interaction.formatted_text))
            _record_decision(db, interaction.id, c, "create", "Candidate passed generic admission policy; context informed but did not dictate the decision.", mem.id)
            actions.append({"action": "create", "memory_id": mem.id, "scope": scope})

    db.commit()
    return {"candidates": candidates, "actions": actions, "model_usage": usage, "invalid_candidates": invalid}
