from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPolicy:
    name: str
    default_scope: str
    sensitivity_bias: str
    durable_signals: tuple[str, ...]
    never_store_patterns: tuple[str, ...]
    notes: str


# Context is evidence, not a hard partition. An explicit global fact remains a global fact even if
# it happened to be spoken in VS Code. These policies help the extractor judge relevance/scope.
POLICIES: dict[str, ContextPolicy] = {
    "developer": ContextPolicy(
        name="developer",
        default_scope="work:developer",
        sensitivity_bias="high",
        durable_signals=("tool preference", "project", "framework", "coding preference", "correction"),
        never_store_patterns=("api key", "token", "secret", "password", "private key", "credential"),
        notes="Developer context increases usefulness of durable workflow/project preferences, but credentials and one-off debug values are never durable memory.",
    ),
    "email": ContextPolicy(
        name="email",
        default_scope="work:email",
        sensitivity_bias="medium",
        durable_signals=("recipient relationship", "tone preference", "signature preference", "project"),
        never_store_patterns=("otp", "password", "bank account", "card number", "cvv"),
        notes="Email context strengthens communication-preference evidence; financial and credential-like content is excluded by default.",
    ),
    "work messaging": ContextPolicy(
        name="work messaging",
        default_scope="work:messaging",
        sensitivity_bias="medium",
        durable_signals=("role", "relationship", "project", "deadline", "workflow", "correction"),
        never_store_patterns=("password", "token", "secret"),
        notes="Useful source for evolving work-world facts and episodes; conversational chatter is not automatically memory.",
    ),
    "personal messaging": ContextPolicy(
        name="personal messaging",
        default_scope="personal:messaging",
        sensitivity_bias="high",
        durable_signals=("explicit preference", "explicit remember request", "correction"),
        never_store_patterns=("password", "otp", "financial account", "medical diagnosis"),
        notes="Personal chats receive a higher admission bar because they contain dense sensitive and transient information.",
    ),
    "other": ContextPolicy(
        name="other",
        default_scope="global",
        sensitivity_bias="medium",
        durable_signals=("explicit fact", "preference", "relationship", "project", "correction"),
        never_store_patterns=("password", "otp", "api key", "token", "secret", "private key"),
        notes="Generic conservative fallback. The system must still work when Style/app metadata is missing or unknown.",
    ),
}

ALIASES = {
    "work": "work messaging",
    "slack": "work messaging",
    "teams": "work messaging",
    "personal": "personal messaging",
    "messaging": "personal messaging",
    "dev": "developer",
    "coding": "developer",
}


def policy_for(style_context: str | None) -> ContextPolicy:
    key = (style_context or "other").strip().lower()
    key = ALIASES.get(key, key)
    return POLICIES.get(key, POLICIES["other"])
