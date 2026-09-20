"""Pack-local citations and bounded deterministic answer support checks.

No database writes or relaxed source eligibility: input is already privacy-filtered.
"""
from datetime import datetime, timedelta, timezone
import json
import re
from pydantic import BaseModel, ConfigDict, Field


class HandleClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    evidence: list[str] = Field(min_length=1)


class HandleAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=1, max_length=4000)
    supported: bool
    claims: list[HandleClaim] = Field(default_factory=list)
    applied_preferences: list[str] = Field(default_factory=list)


def necessary_evidence(query, plan, memories, history):
    if plan.intent != "draft":
        return memories, history

    memory_management = bool(re.search(
        r"\b(forget|forgot|forgotten|remember|memory|retain|retained|delete|deleted|"
        r"don't remember|do not remember|don't retain|do not retain|keep .* forgotten)\b",
        query,
        re.I,
    ))

    requested_predicates = {
        str(p).casefold() for p in (getattr(plan, "predicates", None) or [])
    }

    tool_predicates = {
        "uses",
        "uses_equipment",
        "format",
        "tool",
        "tools",
        "tool_preference",
        "technology",
    }

    tool = (
        bool(re.search(
            r"\b(tool|tools|equipment|format|technology|technologies|material|materials|standard|standards)\b",
            query,
            re.I,
        ))
        or any(
            p.startswith("uses_") or p in tool_predicates
            for p in requested_predicates
        )
    )

    date = (
        bool(re.search(
            r"\b(date|deadline|delivery|due|timing)\b",
            query,
            re.I,
        ))
        or any(
            any(t in p for t in ("deadline", "due", "delivery", "scheduled"))
            for p in requested_predicates
        )
    )

    people = bool(re.search(
        r"\b(team|people|person|who|collaborators|coordinator|reviewer)\b", query, re.I))
    episodes = bool(re.search(
        r"\b(incident|issue|problem|investigat|resolved|history|timeline|happened)", query, re.I))

    def useful(m):
        if m["type"] == "preference":
            return True
        p = m["predicate"].casefold()

        text = " ".join(
            str(m.get(k, ""))
            for k in ("canonical_text", "subject", "predicate", "value")
        ).casefold()

        lifecycle_instruction = (
            p in {
                "forget",
                "forgotten",
                "memory_instruction",
                "retention_instruction",
                "non_retention",
                "delete_memory",
            }
            or bool(re.search(
                r"\b(forget|forgotten|do not remember|don't remember|"
                r"do not retain|don't retain|keep .* forgotten)\b",
                text,
                re.I,
            ))
        )

        # Lifecycle/audit instructions remain stored and inspectable, but they are
        # not content for an unrelated email/update/briefing.
        if lifecycle_instruction and not memory_management:
            return False

        if tool or date:
            return tool and (p.startswith("uses_") or p in {"uses", "uses_equipment", "format", "tool", "tools", "tool_preference", "technology"}) or date and any(t in p for t in ("deadline", "due", "delivery", "scheduled")) or people and m["type"] == "relationship" or episodes and m["type"] == "episode"
        if m["type"] == "episode" or "root_cause" in p:
            return episodes
        if not people and p in {"reviews", "collaborates_on", "alias"}:
            return False
        return True
    chosen = [m for m in memories if useful(m)]
    return chosen, history if episodes or plan.time_from or plan.time_until else []


def evidence_handles(memories, history):
    mapping = {}
    public = []
    identities = {}
    for kind, records in (("memory", memories), ("history", history)):
        for record in records:
            h = f"E{len(mapping)+1}"
            mapping[h] = {"kind": kind, "record": record}
            if kind == "history":
                item = {k: v for k, v in record.items() if k not in {
                    "interaction_id", "score"}}
            else:
                item = {k: v for k, v in record.items() if k not in {"memory_id", "source_interaction_ids",
                                                                     "score", "source_evidence", "subject_entity_id", "value_entity_id"}}
                item["sources"] = [{k: v for k, v in e.items() if k not in {
                    "interaction_id", "alias_binding"}} for e in record["source_evidence"]]
                for side in ("subject", "value"):
                    identity = record.get(side+"_entity_id")
                    if identity is not None:
                        identities.setdefault(
                            identity, f"P{len(identities)+1}")
                        item[side+"_identity"] = identities[identity]
            public.append({"handle": h, "kind": kind, **item})
    return public, mapping


def handle_schema(mapping):
    schema = HandleAnswer.model_json_schema()
    if mapping:
        schema["$defs"]["HandleClaim"]["properties"]["evidence"]["items"] = {
            "type": "string", "enum": list(mapping)}
        prefs = [h for h, v in mapping.items() if v["kind"] ==
                 "memory" and v["record"]["type"] == "preference"]
        if prefs:
            schema["properties"]["applied_preferences"]["items"] = {
                "type": "string", "enum": prefs}
        else:
            schema["properties"]["applied_preferences"]["maxItems"] = 0
    return schema


def map_answer(raw, mapping):
    answer = HandleAnswer.model_validate(raw)
    if answer.supported and not answer.claims:
        raise ValueError(
            "Supported factual answer needs evidence-linked claims")
    usedm = set()
    usedi = set()
    claims = []

    def ids(handles):
        mids = set()
        iids = set()
        for h in handles:
            if h not in mapping:
                raise ValueError("Out-of-pack evidence handle: "+h)
            v = mapping[h]
            r = v["record"]
            if v["kind"] == "memory":
                mids.add(r["memory_id"])
                iids.update(e["interaction_id"] for e in r["source_evidence"])
            else:
                iids.add(r["interaction_id"])
        usedm.update(mids)
        usedi.update(iids)
        return sorted(mids), sorted(iids)
    for c in answer.claims:
        m, i = ids(c.evidence)
        claims.append({"text": c.text, "memory_ids": m, "interaction_ids": i})
    for h in answer.applied_preferences:
        if h not in mapping or mapping[h]["kind"] != "memory" or mapping[h]["record"]["type"] != "preference":
            raise ValueError("Applied preference is not a supplied preference")
    ids(answer.applied_preferences)
    return {"answer": answer.answer, "supported": answer.supported, "claims": claims, "used_memory_ids": sorted(usedm), "used_interaction_ids": sorted(usedi)}


def moment(value):
    d = datetime.fromisoformat(value.replace(
        "Z", "+00:00")) if isinstance(value, str) else value
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


RELATIVE = re.compile(
    r"\b(earlier this week|this week|just completed|today|yesterday|currently|recently|still)\b", re.I)
EVENT = re.compile(
    r"\b(completed|resolved|investigated|prepared|sent|met|finished|started|arrived|spent|worked|reviewed|became|took over)\b", re.I)


def is_ongoing_state(r, claim):
    """True when a stored memory represents a state that still holds now."""
    if (
        r.get("status") != "active"
        or r.get("certainty") != "confirmed"
        or r.get("temporal_status") != "current"
    ):
        return False

    # Explicit event language remains event-like even if the broad memory
    # classifier stored the record as current.
    if EVENT.search(claim):
        return False

    canonical = str(r.get("canonical_text", ""))
    if EVENT.search(canonical):
        return False

    return True


def temporal_support(claim, records, now):
    now = moment(now)
    issues = []
    for term in {m.group(0).lower() for m in RELATIVE.finditer(claim)}:
        supported = False
        quoted = re.findall(r"[\"'“](.*?)[\"'”]", claim)
        for wrapped in records:
            r = wrapped["record"]
            spans = r.get("source_evidence", []) if wrapped["kind"] == "memory" else [
                {"excerpt": r.get("formatted_text", ""), "occurred_at": r["occurred_at"]}]
            for span in spans:
                d = moment(span["occurred_at"])
                labels = {d.strftime("%B ")+str(d.day) +
                          d.strftime(", %Y"), d.date().isoformat()}
                if any(label.casefold() in claim.casefold() for label in labels) and any(term in q.casefold() and q in span["excerpt"] for q in quoted):
                    supported = True
        for wrapped in records:
            r = wrapped["record"]
            dates = [moment(e["occurred_at"]) for e in r.get("source_evidence", [
            ])] if wrapped["kind"] == "memory" else [moment(r["occurred_at"])]
            if r.get("type") == "episode" and r.get("valid_from"):
                dates = [moment(r["valid_from"])]
            is_event = (
                wrapped["kind"] == "history"
                or bool(EVENT.search(claim))
                or (
                    r.get("type") == "episode"
                    and not is_ongoing_state(r, claim)
                )
            )
            active = wrapped["kind"] == "memory" and r.get("status") == "active" and r.get("certainty") == "confirmed" and r.get("temporal_status") == "current" and (
                not r.get("valid_from") or moment(r["valid_from"]) <= now) and (not r.get("valid_until") or moment(r["valid_until"]) > now)
            if term in {"currently", "still"} and active and not is_event:
                supported = True
            elif term == "today" and active and not is_event:
                supported = True
            elif not is_event and wrapped["kind"] == "memory" and r.get("certainty") == "confirmed" and r.get("valid_from") and term in {"yesterday", "this week", "earlier this week"}:
                start = (now-timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0) if term == "yesterday" else (
                    now-timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                end = start+timedelta(days=1) if term == "yesterday" else now
                valid_end = moment(r["valid_until"]) if r.get(
                    "valid_until") else now
                supported = moment(r["valid_from"]) < end and valid_end > start
            elif is_event:
                for d in dates:
                    if d > now:
                        continue
                    delta = now-d
                    if term == "today" and d.date() == now.date():
                        supported = True
                    elif term == "yesterday" and d.date() == (now-timedelta(days=1)).date():
                        supported = True
                    elif term in {"this week", "earlier this week"} and d.date() >= now.date()-timedelta(days=now.weekday()) and (term != "earlier this week" or d < now):
                        supported = True
                    elif term == "recently" and delta <= timedelta(days=7):
                        supported = True
                    elif term == "just completed" and delta <= timedelta(hours=24):
                        supported = True
                    elif term in {"currently", "still"} and active and d.date() == now.date():
                        supported = True
        if not supported:
            issues.append("Unsupported relative time: "+term)
    return issues


def deterministic_support(raw, mapping, now):
    issues = []
    for c in raw.get("claims", []):
        records = [mapping[h] for h in c.get("evidence", []) if h in mapping]
        issues.extend(temporal_support(c["text"], records, now))
    # Bind answer-only temporal wording to a matching claim; do not require identical prose.

    def words(text):
        stop = {"the", "a", "an", "is", "are", "was", "were", "of", "on", "in", "to", "for", "and", "i", "we", "you",
                "my", "your", "it", "its", "currently", "still", "today", "yesterday", "recently", "this", "week", "earlier"}
        return {"coordinate" if t.startswith("coordinat") else t for t in re.findall(r"[^\W_]+", text.casefold()) if t not in stop}
    full = raw.get("answer", "")
    declared = " ".join(c["text"] for c in raw.get("claims", [])).lower()
    all_used = [mapping[h] for c in raw.get(
        "claims", []) for h in c.get("evidence", []) if h in mapping]
    for term in RELATIVE.findall(full):
        if term.lower() in declared:
            continue
        # A dated direct quotation anchors words like Today to the quoted source.
        quotes = re.findall(r"[\"'“](.*?)[\"'”]", full)
        quoted = any(term.casefold() in q.casefold() for q in quotes)
        if quoted and not temporal_support(full, all_used, now):
            continue
        valid = False
        for sentence in re.split(r"[.!?\n]+", full):
            if not re.search(r"\b"+re.escape(term)+r"\b", sentence, re.I):
                continue
            tokens = words(sentence)
            for c in raw.get("claims", []):
                overlap = tokens & words(c["text"])
                records = [mapping[h]
                           for h in c.get("evidence", []) if h in mapping]
                if len(overlap) >= 2 and len(overlap)/max(1, len(tokens)) >= .7 and not temporal_support(sentence, records, now):
                    valid = True
        if not valid:
            issues.append("Unsupported answer-only relative time: "+term)
    names = {}
    for v in mapping.values():
        if v["kind"] != "memory":
            continue
        r = v["record"]
        for side in ("subject", "value"):
            eid = r.get(side+"_entity_id")
            q = r.get(side+"_qualifier", "")
            name = r.get(side, "")
            if eid and q:
                names.setdefault(name.casefold(), {})[eid] = q
    answer = raw.get("answer", "").casefold()
    used = {h for c in raw.get("claims", []) for h in c.get("evidence", [])}
    for name, identities in names.items():
        if len(identities) < 2 or not re.search(r"(?<!\w)"+re.escape(name)+r"(?!\w)", answer):
            continue
        involved = set()
        for h in used:
            r = mapping.get(h, {}).get("record", {})
            involved.update(r.get(s+"_entity_id")
                            for s in ("subject", "value") if r.get(s, "").casefold() == name)
        needed = [identities[i] for i in involved if i in identities]
        if any(q.casefold() not in answer for q in needed) or len(re.findall(r"(?<!\w)"+re.escape(name)+r"(?!\w)", answer)) < len(needed):
            issues.append("Ambiguous same-name rendering: "+name)
    # Explicit invented deliverables/commitments are not generic polite phrasing.
    sources = " ".join(e["excerpt"] for v in mapping.values() for e in v["record"].get(
        "source_evidence", []))+" "+" ".join(v["record"].get("formatted_text", "") for v in mapping.values())
    for pattern in [r"\battach(?:ed|ment|ments)\b", r"\b(?:we|i) (?:will|promise to|commit to)\b", r"\b(?:continuing to|continue to) monitor\b"]:
        if re.search(pattern, answer, re.I) and not re.search(pattern, sources, re.I):
            issues.append("Unsupported attachment or commitment")
    return sorted(set(issues))


def render_draft(raw):
    """Every rendered draft sentence is an evidence-linked claim, not free prose.

    Style remains model-generated within each supported sentence. No automatic repair of
    invalid references: map_answer and semantic verification still validate every claim.
    """
    clean = HandleAnswer.model_validate(raw).model_dump()
    if clean["supported"] and clean["claims"]:
        clean["answer"] = "\n\n".join(c["text"].strip()
                                      for c in clean["claims"])
    return clean
