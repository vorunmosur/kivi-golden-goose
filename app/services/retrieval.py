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
    sensitive_terms = (
        "password", "passcode", "otp", "cvv", "api key", "access token",
        "refresh token", "private key", "secret key", "bank account",
        "passport number", "aadhaar", "social security number", "medical diagnosis",
    )
    if any(term in text for term in sensitive_terms):
        return False
    if re.search(r"\bsk-[a-z0-9_-]{10,}\b", text, re.I):
        return False
    if re.search(r"\b(?:\d[ -]*?){13,19}\b", text):
        return False
    return True


def lexical_score(query: str, text: str) -> float:
    q = _tokenize(query)
    d = _tokenize(text)
    if not q or not d:
        return 0.0
    return len(q & d) / math.sqrt(len(q) * len(d))


def _cosine(qv: np.ndarray, mv: np.ndarray) -> float:
    return float(np.dot(qv, mv) / ((np.linalg.norm(qv) or 1.0) * (np.linalg.norm(mv) or 1.0)))


def retrieve_memories(db: Session, query: str, k: int = 8) -> tuple[list[tuple[Memory, float]], float]:
    start = time.perf_counter()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    memories = db.scalars(select(Memory).where(Memory.status == "active")).all()
    memories = [m for m in memories if not m.expires_at or m.expires_at > now]
    if not memories:
        return [], (time.perf_counter() - start) * 1000

    lexical = np.array([lexical_score(query, f"{m.predicate} {m.value} {m.canonical_text} {m.scope}") for m in memories])
    semantic = np.zeros(len(memories), dtype=float)

    if provider.enabled:
        try:
            missing = [m for m in memories if not m.embedding_json]
            if missing:
                vecs = provider.embed([m.canonical_text for m in missing])
                for m, v in zip(missing, vecs):
                    m.embedding_json = json.dumps(v)
                db.commit()
            qv = np.array(provider.embed([query])[0], dtype=float)
            for i, m in enumerate(memories):
                semantic[i] = _cosine(qv, np.array(json.loads(m.embedding_json), dtype=float))
        except Exception:
            semantic[:] = 0.0

    if semantic.max(initial=0) > 0:
        # lexical prevents semantically broad but unrelated memories from dominating
        scores = 0.68 * semantic + 0.32 * lexical
    else:
        scores = lexical

    order = np.argsort(scores)[::-1]
    # Repeated memories from one broad predicate must not crowd every other evidence type out of
    # a compound request. A small per-predicate cap keeps retrieval diverse while preserving the
    # top scoring alternatives for genuinely multi-valued knowledge.
    predicate_counts: Counter[str] = Counter()
    ranked = []
    for i in order:
        if scores[i] <= 0.04:
            continue
        predicate = memories[i].predicate
        if predicate_counts[predicate] >= 2:
            continue
        ranked.append((memories[i], float(scores[i])))
        predicate_counts[predicate] += 1
        if len(ranked) >= k:
            break
    return ranked, (time.perf_counter() - start) * 1000


def retrieve_history(db: Session, query: str, k: int = 8, exclude_ids: set[int] | None = None) -> list[tuple[Interaction, float]]:
    """Fallback episodic/source retrieval over original interactions.

    Semantic memory remains the primary abstraction, but arbitrary hidden-eval questions may ask
    about a one-off episode that should not have been promoted to durable memory. Source-history
    retrieval lets Hey Kivi answer from evidence without polluting long-term memory.
    """
    exclude_ids = exclude_ids or set()
    interactions = db.scalars(select(Interaction).order_by(Interaction.occurred_at.desc())).all()
    interactions = [it for it in interactions if it.id not in exclude_ids and _history_is_safe(it)]
    query_tokens = _tokenize(query)
    document_tokens = [
        _tokenize(f"{it.formatted_text} {it.raw_asr} {it.app_context} {it.style_context}")
        for it in interactions
    ]
    document_frequency = Counter(token for tokens in document_tokens for token in tokens)
    corpus_size = max(1, len(interactions))

    def weighted_overlap(tokens: set[str]) -> float:
        if not query_tokens or not tokens:
            return 0.0
        shared = query_tokens & tokens
        numerator = sum(math.log((corpus_size + 1) / (document_frequency[t] + 1)) + 1 for t in shared)
        q_norm = math.sqrt(sum((math.log((corpus_size + 1) / (document_frequency.get(t, 0) + 1)) + 1) ** 2 for t in query_tokens))
        d_norm = math.sqrt(sum((math.log((corpus_size + 1) / (document_frequency[t] + 1)) + 1) ** 2 for t in tokens))
        return numerator / ((q_norm * d_norm) or 1.0)

    scored: list[tuple[Interaction, float]] = []
    for it, tokens in zip(interactions, document_tokens):
        score = weighted_overlap(tokens)
        if score > 0.04:
            scored.append((it, score))
    scored.sort(key=lambda x: (x[1], x[0].occurred_at), reverse=True)
    return scored[:k]


def retrieve(db: Session, query: str, k: int = 8) -> tuple[list[Memory], float]:
    """Backward-compatible memory-only retrieval."""
    ranked, latency = retrieve_memories(db, query, k)
    return [m for m, _ in ranked], latency
