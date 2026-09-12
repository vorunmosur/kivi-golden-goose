from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)

styles = ["developer", "email", "work messaging", "personal messaging", "other", "unknown"]
apps = {
    "developer": "VS Code",
    "email": "Gmail",
    "work messaging": "Slack",
    "personal messaging": "WhatsApp",
    "other": "Notes",
    "unknown": "Unknown App",
}
people = ["Rajeev", "Aaditya", "Priya", "Maya", "Arjun", "Neha"]
projects = ["Golden Goose", "Atlas", "Orion", "Falcon", "Pulse"]
base = datetime(2026, 9, 1, 9, 0)
records: list[dict] = []

# Deliberately includes context-specific and context-agnostic high-signal cases.
seeded = [
    {
        "style": "work messaging", "app": "Slack",
        "raw_asr": "rajeev is my manager", "formatted_output": "Rajeev is my manager.",
        "case": "global_relationship_from_context", "expected": "save",
    },
    {
        "style": "developer", "app": "VS Code",
        "raw_asr": "im working on golden goose", "formatted_output": "I'm working on Golden Goose.",
        "case": "project_context", "expected": "save",
    },
    {
        "style": "email", "app": "Gmail",
        "raw_asr": "i prefer short direct emails to my manager", "formatted_output": "I prefer short, direct emails to my manager.",
        "case": "scoped_preference", "expected": "save",
    },
    {
        "style": "other", "app": "Notes",
        "raw_asr": "the deadline for golden goose is friday", "formatted_output": "The deadline for Golden Goose is Friday.",
        "case": "generic_fact", "expected": "save",
    },
    {
        "style": "unknown", "app": "Unknown App",
        "raw_asr": "correction the golden goose deadline moved to saturday", "formatted_output": "Correction: the Golden Goose deadline moved to Saturday.",
        "case": "generic_correction_unknown_style", "expected": "update",
    },
    {
        "style": "developer", "app": "VS Code",
        "raw_asr": "use this api key sk THIS SHOULD NEVER BE SAVED 1234567890", "formatted_output": "Use this API key: sk-THIS-SHOULD-NEVER-BE-SAVED-1234567890.",
        "case": "secret", "expected": "reject",
    },
    {
        "style": "unknown", "app": "Unknown App",
        "raw_asr": "my manager changed from rajeev to priya", "formatted_output": "My manager changed from Rajeev to Priya.",
        "case": "generic_relationship_update", "expected": "update",
    },
    {
        "style": "personal messaging", "app": "WhatsApp",
        "raw_asr": "nice weather today", "formatted_output": "Nice weather today.",
        "case": "irrelevant_chatter", "expected": "ignore",
    },
]

for i, item in enumerate(seeded):
    records.append({
        "raw_asr": item["raw_asr"],
        "formatted_output": item["formatted_output"],
        "timestamp": (base + timedelta(minutes=i * 20)).isoformat(),
        "style": item["style"],
        "app": item["app"],
        "session_id": "seeded",
        "metadata": {"source": "synthetic", "case": item["case"], "expected": item["expected"]},
    })

# Mix useful, irrelevant, temporary, sensitive and unknown-context material.
for i in range(len(records), 500):
    style = random.choice(styles)
    app = apps[style]
    person = random.choice(people)
    project = random.choice(projects)
    kind = random.randrange(16)
    expected = "model_judgment"
    if kind == 0:
        raw = f"im also contributing to the {project.lower()} rollout"
        formatted = f"I'm also contributing to the {project} rollout."
        expected = "save"
    elif kind == 1:
        raw = f"remember that {person.lower()} handles design reviews"
        formatted = f"Remember that {person} handles design reviews."
        expected = "save"
    elif kind == 2:
        raw = "i prefer concise bullet point updates"
        formatted = "I prefer concise bullet-point updates."
        expected = "save"
    elif kind == 3:
        raw = f"meet {person.lower()} at three tomorrow"
        formatted = f"Meet {person} at 3 PM tomorrow."
        expected = "temporary_or_ignore"
    elif kind == 4:
        raw = "that coffee was actually pretty good"
        formatted = "That coffee was actually pretty good."
        expected = "ignore"
    elif kind == 5:
        raw = "my otp is one two three four five six"
        formatted = "My OTP is 123456."
        expected = "reject"
    elif kind == 6:
        raw = f"{project.lower()} uses fast api for the backend"
        formatted = f"{project} uses FastAPI for the backend."
        expected = "save"
    elif kind == 7:
        raw = f"actually {person.lower()} is reviewing {project.lower()} now"
        formatted = f"Actually, {person} is reviewing {project} now."
        expected = "save_or_clarify"
    elif kind == 8:
        raw = "i usually send updates before standup"
        formatted = "I usually send updates before stand-up."
        expected = "clarify_or_save_pattern"
    elif kind == 9:
        raw = f"{person.lower()} mentioned {project.lower()} once in passing"
        formatted = f"{person} mentioned {project} once in passing."
        expected = "ignore"
    elif kind == 10:
        raw = "my home city is pune"
        formatted = "My home city is Pune."
        expected = "save"
    elif kind == 11:
        raw = "i prefer vegetarian food for team lunches"
        formatted = "I prefer vegetarian food for team lunches."
        expected = "save"
    elif kind == 12:
        raw = "the staging password is temporary password four two"
        formatted = "The staging password is temporary-password-42."
        expected = "reject"
    elif kind == 13:
        raw = "i parked on level three today"
        formatted = "I parked on level three today."
        expected = "temporary_or_ignore"
    elif kind == 14:
        raw = f"{person.lower()} works in the singapore time zone"
        formatted = f"{person} works in the Singapore time zone."
        expected = "save"
    else:
        raw = "maybe i like longer reports but im not sure"
        formatted = "Maybe I like longer reports, but I'm not sure."
        expected = "clarify_or_ignore"

    records.append({
        "raw_asr": raw,
        "formatted_output": formatted,
        "timestamp": (base + timedelta(minutes=i * 7)).isoformat(),
        "style": style,
        "app": app,
        "session_id": f"s{i // 20}",
        "metadata": {"source": "synthetic", "case": "mixed", "expected": expected},
    })

out = Path(__file__).resolve().parents[1] / "data" / "dev_corpus.jsonl"
out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records), encoding="utf-8")
print(f"wrote {len(records)} records to {out}")
