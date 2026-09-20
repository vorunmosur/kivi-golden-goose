import json
import os
import time
from pathlib import Path

from app.db import SessionLocal
from app.services.hey_kivi import answer_query


CASES = [
    {
        "id": "current_manager",
        "query": "Who is my current manager?",
        "required": ["priya"],
        "forbidden": ["rajeev"],
    },
    {
        "id": "corrected_deadline",
        "query": "What is the current deadline for Golden Goose?",
        "required": ["saturday"],
        "forbidden": ["friday"],
    },
    {
        "id": "semantic_home_city",
        "query": "Which city do I live in?",
        "required": ["pune"],
        "forbidden": [],
    },
    {
        "id": "project_technology",
        "query": "What backend technology does Orion use?",
        "required": ["fastapi"],
        "forbidden": [],
    },
    {
        "id": "aggregate_projects",
        "query": "Summarize the current projects you know about.",
        "required": ["golden goose", "falcon", "orion", "atlas"],
        "forbidden": [],
    },
    {
        "id": "project_relationship",
        "query": "Who reviews Falcon?",
        "required_any": ["aaditya", "priya", "maya"],
        "forbidden": [],
    },
    {
        "id": "distributed_project_facts",
        "query": "What do you know about Golden Goose's deadline and backend technology?",
        "required": ["saturday", "fastapi"],
        "forbidden": ["friday"],
    },
    {
        "id": "explicit_email_preference",
        "query": "How do I prefer my emails or work updates to be written?",
        "required_any": ["concise", "short", "bullet"],
        "forbidden": [],
    },
    {
        "id": "tentative_not_promoted",
        "query": "Have I confirmed that I prefer longer reports?",
        "required_any": [
            "tentative",
            "not confirmed",
            "haven't confirmed",
            "have not confirmed",
            "don't know",
            "do not know",
        ],
        "forbidden": ["you prefer longer reports."],
    },
    {
        "id": "unsupported_private",
        "query": "What is my passport number?",
        "required_any": [
            "don't know",
            "do not know",
            "not in",
            "no saved",
            "cannot",
            "can't",
        ],
        "forbidden": [],
    },
    {
        "id": "grounded_manager_update",
        "query": "Draft a concise update to my manager saying Golden Goose is due Saturday and uses FastAPI.",
        "required": ["saturday", "fastapi"],
        "required_any": ["priya", "golden goose"],
        "forbidden": ["friday", "rajeev"],
    },
]


def normalize(text):
    return " ".join(str(text).casefold().split())


def score(case, response):
    text = normalize(response)

    required = [normalize(x) for x in case.get("required", [])]
    required_any = [normalize(x) for x in case.get("required_any", [])]
    forbidden = [normalize(x) for x in case.get("forbidden", [])]

    missing = [x for x in required if x not in text]
    any_ok = True if not required_any else any(x in text for x in required_any)
    forbidden_hits = [x for x in forbidden if x in text]

    passed = not missing and any_ok and not forbidden_hits

    return {
        "passed": passed,
        "missing_required": missing,
        "required_any_satisfied": any_ok,
        "forbidden_hits": forbidden_hits,
    }


def main():
    db_path = os.environ.get("KIVI_DB_PATH")
    if not db_path:
        raise SystemExit("KIVI_DB_PATH is not set.")

    output_dir = Path("eval/post500-semantic-challenge-post-hardening")
    output_dir.mkdir(parents=True, exist_ok=True)

    db = SessionLocal()
    results = []

    try:
        for i, case in enumerate(CASES, 1):
            print(f"[{i}/{len(CASES)}] {case['id']}: {case['query']}")
            started = time.perf_counter()

            try:
                result = answer_query(
                    db,
                    case["query"],
                    session_id="post500-semantic-challenge",
                )
                latency_ms = (time.perf_counter() - started) * 1000

                response = result.get("response", "")
                scored = score(case, response)

                entry = {
                    "id": case["id"],
                    "query": case["query"],
                    "response": response,
                    "passed": scored["passed"],
                    "missing_required": scored["missing_required"],
                    "required_any_satisfied": scored["required_any_satisfied"],
                    "forbidden_hits": scored["forbidden_hits"],
                    "reason": result.get("reason"),
                    "memories": result.get("memories", []),
                    "history_evidence": result.get("history_evidence", []),
                    "model_usage": result.get("model_usage", {}),
                    "latency_ms": latency_ms,
                }

            except Exception as exc:
                db.rollback()
                entry = {
                    "id": case["id"],
                    "query": case["query"],
                    "response": "",
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }

            results.append(entry)

            mark = "PASS" if entry["passed"] else "FAIL"
            print(f"    {mark}: {entry.get('response', '')}")
            print()

    finally:
        db.close()

    passed = sum(1 for r in results if r["passed"])

    summary = {
        "run_kind": "post500_frozen_state_semantic_challenge",
        "database": db_path,
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0,
        "note": (
            "Query-side validation against a copy of the frozen 500-record "
            "database. No re-ingestion performed."
        ),
    }

    (output_dir / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("=" * 60)
    print(f"RESULT: {passed}/{len(results)} passed")
    print(f"Saved: {output_dir / 'summary.json'}")
    print(f"Saved: {output_dir / 'results.json'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
