from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from datetime import datetime, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Interaction, Memory
from app.services.provider import provider


def _tokenize(text: str) -> set[str]:
    stop = {"the", "and", "that", "this", "with", "from", "what", "when", "where", "who", "how", "your", "about", "have", "does", "did", "are", "was", "for", "you", "my"}
    aliases = {
        "met": "meeting", "meet": "meeting", "meets": "meeting",
        "boss": "manager", "supervisor": "manager", "reports": "manager",
        "due": "deadline", "deliverable": "deadline",
        "likes": "prefer", "preferred": "prefer", "prefers": "prefer",
        "emails": "email", "messages": "message",
        "projects": "project", "working": "work",
    }
    tokens = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) <= 2 or token in stop:
            continue
        token = aliases.get(token, token)
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.add(token)
    return tokens


def _history_is_safe(interaction: Interaction) -> bool:
    """Source history is evidence, but private sessions and secrets are never retrieval data."""
    if interaction.hide_mode:
        return False
    text = f"{interaction.formatted_text} {interaction.raw_asr}".lower()
    from app.services.memory_engine import _looks_sensitive
    return not _looks_sensitive(text,())


def lexical_score(query: str, text: str) -> float:
    q = _tokenize(query)
    d = _tokenize(text)
    if not q or not d:
        return 0.0
    return len(q & d) / math.sqrt(len(q) * len(d))


def _cosine(qv: np.ndarray, mv: np.ndarray) -> float:
    return float(np.dot(qv, mv) / ((np.linalg.norm(qv) or 1.0) * (np.linalg.norm(mv) or 1.0)))



def history_blocked(db, interaction):
    from app.models import ForgetBoundary, MemorySource
    from app.services.entities import normalize
    if interaction.retrieval_blocked or not _history_is_safe(interaction): return True
    if re.search(r"\b(?:don't|do not|never) (?:remember|store|retain)\b",interaction.formatted_text,re.I): return True
    # Exclude lifecycle-bearing full transcripts: an old clause could contradict current state.
    represented=db.scalars(select(MemorySource).where(MemorySource.interaction_id==interaction.id)).all()
    if any(link.memory.status in {"superseded","deleted","expired","tentative","future"} for link in represented): return True
    text=normalize(interaction.formatted_text+" "+interaction.raw_asr)
    for b in db.scalars(select(ForgetBoundary)):
        if interaction.occurred_at>b.occurred_at: continue
        return True  # Conservative full-transcript boundary: paraphrases cannot resurrect a forgotten fact.
        topic=normalize(b.predicate).replace("_"," ")
        if b.value and normalize(b.value) in text: return True
        if any(t in _tokenize(topic) for t in _tokenize(text)): return True
        if b.subject!="user" and b.subject in text: return True
    return False


def vector_scores(db, query, rows, texts, errors):
    from app.config import settings
    if not provider.enabled or not rows: return [0.0]*len(rows)
    try:
        missing=[(row,text) for row,text in zip(rows,texts) if not row.embedding_json or row.embedding_model!=settings.embedding_model]
        for offset in range(0,len(missing),32):
            batch=missing[offset:offset+32]; vectors=provider.embed([text for _,text in batch])
            if len(vectors)!=len(batch): raise ValueError("Embedding result count mismatch")
            for (row,_),vector in zip(batch,vectors):
                if not vector or not np.isfinite(vector).all(): raise ValueError("Invalid embedding")
                row.embedding_json=json.dumps(vector);row.embedding_model=settings.embedding_model
        qv=np.asarray(provider.embed([query])[0],dtype=float)
        scores=[]
        for row in rows:
            vector=np.asarray(json.loads(row.embedding_json),dtype=float)
            if vector.shape!=qv.shape: raise ValueError("Embedding dimension mismatch; rebuild model vectors")
            scores.append(max(0.0,_cosine(qv,vector)))
        db.flush()
        return scores
    except Exception as error:
        errors.append({"component":"embeddings","error":str(error),"fallback":"lexical"})
        return [0.0]*len(rows)


def project_names(db):
    from app.models import Entity
    names={e.name for e in db.scalars(select(Entity)) if e.kind=="project"}
    for m in db.scalars(select(Memory)):
        fields=json.loads(m.scope) if m.scope.startswith("{") else {}
        if fields.get("project"): names.add(fields["project"])
    return names


def project_anchors(db,query,plan):
    from app.services.entities import literal_present,normalize
    known=project_names(db)
    names={normalize(n) for n in known if literal_present(n,query)}
    if plan.project: names.add(normalize(plan.project))
    return names


def anchored_memory(m,anchors):
    from app.services.entities import literal_present,normalize
    if not anchors:return True
    fields=json.loads(m.scope) if m.scope.startswith("{") else {}
    if fields.get("project") and normalize(fields["project"]) not in anchors:return False
    return any(normalize(m.subject)==a or normalize(m.value)==a or normalize(fields.get("project", ""))==a
               or any(literal_present(a,source.evidence_text) for source in m.sources) for a in anchors)


def predicate_key(value):
    # Retrieval equivalence only; never rewrite stored relationships or their direction.
    forms={"coordinates":"coordinator","coordinate":"coordinator","coordinated":"coordinator"}
    return tuple(sorted(forms.get(t,t) for t in re.findall(r"[^\W_]+",value.casefold())
                        if t not in {"is","has","of","for","the","a","an","to","in","at","by"}))


def retrieve_memories(db: Session, query: str, k: int = 8, plan=None, entity_ids=None, errors=None, now=None):
    from app.services.query_context import plan_query,scope_matches
    from app.services.lifecycle import expire,boundary_blocks
    start=time.perf_counter();now=now or datetime.now(timezone.utc).replace(tzinfo=None);errors=errors if errors is not None else []
    if plan is None: plan,entity_ids,_=plan_query(db,query,now)
    entity_ids=entity_ids or set();expire(db,now)
    allowed={"active"} if plan.intent in {"current","draft"} else {"active","historical","superseded","expired"} if plan.intent=="historical" else {"active","tentative","future"}
    rows=[m for m in db.scalars(select(Memory).where(Memory.status.in_(allowed))) if not boundary_blocks(db,m) and (m.memory_type!="preference" or scope_matches(m.scope,plan))]
    if plan.intent in {"current","draft"}: rows=[m for m in rows if m.certainty=="confirmed" and m.temporal_status=="current" and (not m.valid_from or m.valid_from<=now)]
    # One relational hop joins a person's project to distributed project facts.
    # A fact can mention a named object before that entity has been admitted.
    # Resolve only exact, unique known names/explicit aliases at read time; never
    # guess an identity from lexical similarity or merge same-name participants.
    from app.services.entities import lookup
    object_ids={}
    resolved={}
    for m in rows:
        if m.value_entity_id:
            object_ids[m.id]=m.value_entity_id
        else:
            if m.value not in resolved:
                found=lookup(db,m.value)
                resolved[m.value]=found[0].id if len(found)==1 else None
            object_ids[m.id]=resolved[m.value]
    anchors=project_anchors(db,query,plan)
    expanded=set(entity_ids)
    if anchors:
        rows=[m for m in rows if anchored_memory(m,anchors) or m.memory_type=="preference" and plan.intent=="draft" and scope_matches(m.scope,plan)]
    else:
        # One-hop person/task expansion must not turn the shared user into a graph hub.
        from app.models import Entity
        def bridge(i):
            e=db.get(Entity,i) if i else None
            return e is not None and e.normalized_name!="user"
        for m in rows:
            if m.subject_entity_id in entity_ids and bridge(object_ids[m.id]): expanded.add(object_ids[m.id])
            if object_ids[m.id] in entity_ids and bridge(m.subject_entity_id): expanded.add(m.subject_entity_id)
        if expanded: rows=[m for m in rows if m.subject_entity_id in expanded or object_ids[m.id] in expanded or m.memory_type=="preference" and plan.intent=="draft"]
    if plan.time_from or plan.time_until:
        def in_window(m):
            if plan.intent=="draft" and m.memory_type=="preference": return True
            if plan.time_axis=="validity":
                end=m.valid_to or m.expires_at
                if m.memory_type=="episode":
                    return bool(m.valid_from and (not plan.time_from or m.valid_from>=plan.time_from) and (not plan.time_until or m.valid_from<plan.time_until))
                return (not plan.time_until or not m.valid_from or m.valid_from<plan.time_until) and (not plan.time_from or not end or end>plan.time_from)
            return any((not plan.time_from or s.interaction.occurred_at>=plan.time_from) and (not plan.time_until or s.interaction.occurred_at<plan.time_until) for s in m.sources)
        rows=[m for m in rows if in_window(m)]
    if plan.app and plan.intent=="historical": rows=[m for m in rows if any(s.interaction.app_context.casefold()==plan.app.casefold() for s in m.sources)]
    if plan.intent=="current" and plan.predicates:
        # Ignore grammatical wrappers when matching planner labels to stored slots.
        # This is retrieval-only: identities, lifecycle and scope remain unchanged.
        requested={predicate_key(p) for p in plan.predicates}
        requested.discard(())
        tool_question=bool(re.search(r"\b(tool|tools|equipment|format|technology|technologies)\b",query,re.I))
        tool_slots={"uses","uses_equipment","format","tool","tools","tool_preference","technology"}
        rows=[m for m in rows if m.predicate in plan.predicates or predicate_key(m.predicate) in requested
              or tool_question and m.predicate in tool_slots]
    texts=[f"{m.subject} {m.predicate} {m.value} {m.canonical_text}" for m in rows]
    semantic=vector_scores(db,query,rows,texts,errors)
    ranked=[]
    for m,text,sem in zip(rows,texts,semantic):
        lex=lexical_score(query,text)
        structured=0.5 if any(predicate_key(m.predicate)==predicate_key(p) for p in plan.predicates) else 0.0
        entity=0.22 if expanded and (m.subject_entity_id in expanded or object_ids[m.id] in expanded) else 0
        pref=0.2 if plan.intent=="draft" and m.memory_type=="preference" else 0
        anchor_bonus=0.35 if anchors and anchored_memory(m,anchors) else 0
        score=anchor_bonus+(0.55*sem+0.3*lex if sem else lex)+structured+entity+pref
        if score>0.10: ranked.append((m,score))
    ranked.sort(key=lambda x:(x[1],x[0].valid_from or datetime.min,x[0].id),reverse=True)
    # A narrower applicable preference overrides the general preference on the same subject/slot.
    chosen={}
    for m,score in ranked:
        if m.memory_type!="preference": continue
        specificity=len(json.loads(m.scope)) if m.scope.startswith("{") else (0 if m.scope=="global" else len(m.scope.split(":")))
        key=(m.subject_entity_id,m.predicate)
        priority=(specificity,m.explicitness=="explicit",m.updated_at)
        if key not in chosen or priority>chosen[key][0]: chosen[key]=(priority,m.id)
    ranked=[(m,s) for m,s in ranked if m.memory_type!="preference" or chosen[(m.subject_entity_id,m.predicate)][1]==m.id]
    # Reserve requested project slots and applicable preferences before a relevance budget.
    if plan.intent=="draft" and anchors:
        selected=[];seen=set()
        for m,score in ranked:
            slot=(m.subject_entity_id,m.predicate,m.memory_type)
            if slot not in seen: selected.append((m,score));seen.add(slot)
        selected.extend((m,score) for m,score in ranked if m.id not in {x.id for x,_ in selected})
        ranked=selected;k=max(k,24)
    elif plan.intent=="historical": k=max(k,16)
    return ranked[:k],(time.perf_counter()-start)*1000


def retrieve_history(db: Session, query: str, k: int = 8, exclude_ids=None, plan=None, entity_ids=None, errors=None, now=None):
    from app.services.query_context import plan_query
    from app.models import Entity,EntityAlias
    errors=errors if errors is not None else []
    if plan is None: plan,entity_ids,_=plan_query(db,query,now)
    # Current truth must never be inferred from an arbitrary unpromoted old transcript.
    if plan.intent=="current": return []
    rows=[it for it in db.scalars(select(Interaction).order_by(Interaction.occurred_at.desc())) if it.id not in (exclude_ids or set()) and not history_blocked(db,it)]
    if plan.app: rows=[it for it in rows if it.app_context.casefold()==plan.app.casefold()]
    if plan.time_from: rows=[it for it in rows if it.occurred_at>=plan.time_from]
    if plan.time_until: rows=[it for it in rows if it.occurred_at<plan.time_until]
    if entity_ids:
        names=[db.get(Entity,i).name.casefold() for i in entity_ids]
        names.extend(db.scalars(select(EntityAlias.alias).where(EntityAlias.entity_id.in_(entity_ids))).all())
        rows=[it for it in rows if any(name in it.formatted_text.casefold() for name in names)]
    anchors=project_anchors(db,query,plan)
    if anchors:
        from app.services.entities import literal_present
        rows=[it for it in rows if any(literal_present(a,it.formatted_text) for a in anchors)]
    semantic=vector_scores(db,query,rows,[it.formatted_text for it in rows],errors)
    scores=[]
    for it,sem in zip(rows,semantic):
        lex=lexical_score(query,it.formatted_text)
        temporal=0.35 if plan.time_from or plan.time_until else 0
        score=(0.7*sem+0.3*lex if sem else lex)+temporal
        if score>0.12: scores.append((it,score))
    scores.sort(key=lambda x:(x[1],x[0].occurred_at),reverse=True)
    return scores[:k]


def retrieve(db: Session, query: str, k: int = 8):
    ranked,latency=retrieve_memories(db,query,k)
    return [m for m,_ in ranked],latency
