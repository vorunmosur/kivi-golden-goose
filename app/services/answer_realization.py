"""Constrained personal-fact realization. Style never rewrites fact sentences.

Inputs must already have passed retrieval privacy/scope eligibility. Unknown slots
are quoted with their recorded date rather than guessed from a predicate name.
"""
from dataclasses import dataclass, asdict
import re


@dataclass(frozen=True)
class Proposition:
    handle: str
    subject: str
    predicate: str
    value: str
    certainty: str
    state: str
    scope: str
    subject_qualifier: str
    value_qualifier: str
    sentence: str


def requests_artifact(query):
    """Recognize an explicit writing artifact even when the model calls it Q&A."""
    if re.search(r"\bbrief\b.+\b(about|on)\b", query, re.I):
        return True
    action = r"\b(write|draft|compose|prepare|send|give|create|summari[sz]e)\b"
    artifact = r"\b(message|note|email|update|briefing|summary|reply)\b"
    return bool(re.search(action, query, re.I) and re.search(artifact, query, re.I))


def qualified(value, qualifier):
    return f"{value} ({qualifier})" if qualifier else value


def realize_uses_predicate(subject, predicate, value):
    """Realize `uses_*` slots without turning boolean values into 'uses true/false'."""
    suffix = predicate.removeprefix("uses").strip("_").replace("_", " ")
    normalized_value = str(value).strip().casefold()

    if normalized_value in {"true", "yes", "1"}:
        return f"{subject} uses {suffix}." if suffix else None

    if normalized_value in {"false", "no", "0"}:
        return f"{subject} does not use {suffix}." if suffix else None

    # For predicates such as uses_irrigation_method=drip lines, the value
    # is the useful object and the predicate suffix is only its category.
    return f"{subject} uses {value}."


def proposition(handle, r):
    subject = qualified(r['subject'], r.get('subject_qualifier', ''))
    value = qualified(r['value'], r.get('value_qualifier', ''))
    predicate = r['predicate'].casefold()
    current = r.get('status') == 'active' and r.get(
        'temporal_status') == 'current'
    confirmed = r.get('certainty') == 'confirmed'
    # Templates deliberately do not infer responsibilities, universality or modality.
    if current and confirmed and predicate.startswith('uses'):
        sentence = realize_uses_predicate(subject, predicate, value)
        if not sentence:
            return None
    elif current and confirmed and predicate in {'format', 'tool', 'tools', 'technology'}:
        sentence = f"The {predicate.replace('_', ' ')} for {subject} is {value}."
    elif current and confirmed and predicate == 'purpose':
        sentence = f"The purpose of {subject} is {value}."
    elif current and confirmed and predicate in {'deadline', 'delivery_date', 'due_date', 'scheduled_delivery'}:
        sentence = f"The recorded {predicate.replace('_', ' ')} for {subject} is {value}."
    elif current and confirmed and predicate in {'coordinator', 'manager', 'owner', 'lead'}:
        sentence = f"The {predicate} of {subject} is {value}."
    else:
        sources = r.get('source_evidence', [])
        if not sources:
            return None
        source = sources[0]
        # A dated quote preserves tense/certainty without promoting history to now.
        sentence = f"Recorded on {source['occurred_at'][:10]}: “{source['excerpt']}”"
    return Proposition(handle, r['subject'], r['predicate'], r['value'], r.get('certainty', ''),
                       r.get('temporal_status', ''), r.get('scope', ''), r.get('subject_qualifier', ''), r.get('value_qualifier', ''), sentence)


def realize_draft(query, mapping):
    """Return immutable fact clauses plus presentation-only scoped style controls."""
    props = []
    preferences = []
    seen = set()
    facets = bool(re.search(
        r'\b(tool|tools|equipment|format|technology|material|materials|standard|standards|date|deadline|delivery|due|timing)\b', query, re.I))
    explicitly_people = bool(
        re.search(r'\b(coordinator|reviewer|collaborators|who)\b', query, re.I))
    for h, wrapped in mapping.items():
        if wrapped['kind'] != 'memory':
            continue
        r = wrapped['record']
        slot = r['predicate'].casefold()
        if r['type'] == 'preference':
            preferences.append((h, r))
            continue
        if slot in {'work_on', 'is_worked_on_by', 'reviews', 'alias', 'collaborates_on'} and not explicitly_people:
            continue
        if facets and not explicitly_people and slot in {'coordinator', 'manager', 'owner', 'lead'}:
            continue
        p = proposition(h, r)
        if p and p.sentence not in seen:
            props.append(p)
            seen.add(p.sentence)
    if not props:
        return None, []
    words = ' '.join(r['value'].casefold() for _, r in preferences)
    # Query presentation requests may override a saved length preference.
    short = bool(re.search(r'\b(short|concise|two.line|brief)\b',
                 query, re.I)) or 'concise' in words
    detailed = 'detailed' in words and not short
    warm = any(w in words for w in ('warm', 'friendly'))
    bullets = any(w in words for w in ('bullet', 'list')) or detailed
    body = ('\n'.join('- '+p.sentence for p in props)
            if bullets else (' ' if short else '\n\n').join(p.sentence for p in props))
    if detailed:
        body = 'Project update\n\n'+body
    if warm:
        body = 'Hello,\n\n'+body+'\n\nThank you!'
    result = {'answer': body, 'supported': True, 'claims': [{'text': p.sentence, 'evidence': [p.handle]} for p in props],
              'applied_preferences': [h for h, _ in preferences]}
    return result, [asdict(p) for p in props]
