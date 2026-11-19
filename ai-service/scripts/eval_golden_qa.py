"""
Golden-QA evaluation harness for the BDC agent.

Runs a set of golden questions against a LIVE ai-service and scores the
verifiability contract:

  1. grounding   - expected_sources=true requires an actual valid citation,
                   not merely a nonempty list of retrieved references.
  2. citation integrity - every inline citation marker must map to an
                   existing reference (no dangling citations).
  3. relevance   - answer must contain the configured keywords (casefold).
  4. aspect mentions - optional must_cover groups detect missing topic mentions;
                   this is not a factual entailment or comprehension score.

Usage (service must be running):
    python scripts/eval_golden_qa.py \
        --base-url http://localhost:8000 \
        --secret $AI_SERVICE_SECRET --user-id 1

Exit code: 0 when all checks pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agents.core.references import validate_inline_citations  # noqa: E402
from app.agents.core.retrieval_evidence import cited_refs  # noqa: E402

GOLDEN_FILE = Path(__file__).resolve().parents[1] / "eval" / "golden_qa.json"


async def run_case(client: httpx.AsyncClient, base_url: str, secret: str,
                   user_id: int, case: dict, course_id: int | None = None) -> dict[str, Any]:
    started = time.monotonic()
    payload = {
        "message": case["message"],
        "agent_type": case.get("agent", "mentor"),
        "user_id": user_id,
        "page_context": {"pageType": case.get("pageType", "other")},
    }
    if case.get("system_context"):
        payload["system_context"] = case["system_context"]
    if course_id is not None:
        payload["course_id"] = course_id
        payload["page_context"]["courseId"] = course_id
    result: dict[str, Any] = {
        "id": case["id"], "ok": True, "failures": [],
        "text": "", "references": [], "model": None,
    }

    text_parts: list[str] = []
    references: list[dict] = []
    async with client.stream(
        "POST", f"{base_url}/ai/agents/chat",
        json=payload, headers={"X-AI-Secret": secret}, timeout=120.0,
    ) as resp:
        if resp.status_code != 200:
            result["ok"] = False
            result["failures"].append(f"HTTP {resp.status_code}")
            return result
        buffer = ""
        async for chunk in resp.aiter_text():
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                etype, data = event.get("type"), event.get("data") or {}
                if etype == "text_delta":
                    text_parts.append(data.get("delta") or "")
                elif etype == "text_reset":
                    text_parts.clear()
                elif etype == "done":
                    references = data.get("references") or []
                    result["model"] = data.get("model")
                    result["retrieval_evidence"] = data.get("retrieval_evidence")

    answer = "".join(text_parts)
    result["text"] = answer
    result["references"] = [r.get("title") for r in references]
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    actual_citations = cited_refs(answer) & set(range(1, len(references) + 1))
    result["cited_sources"] = len(actual_citations)

    # 1. Grounding
    if case.get("expected_sources") and not actual_citations:
        result["ok"] = False
        result["failures"].append("expected grounded citations, not just retrieved references")

    # 2. No fabricated citations
    invalid = validate_inline_citations(answer, len(references))
    if invalid:
        result["ok"] = False
        result["failures"].append(f"dangling citations {invalid} (refs={len(references)})")

    # 3. Keyword relevance
    lowered = answer.casefold()
    missing = [kw for kw in case.get("must_contain", [])
               if kw.casefold() not in lowered]
    if missing:
        result["ok"] = False
        result["failures"].append(f"missing keywords {missing}")

    # 3b. Any-of keywords (soft relevance, e.g. proactive surfaces)
    any_of = [kw for kw in case.get("expect_any", [])]
    if any_of and not any(kw.casefold() in lowered for kw in any_of):
        result["ok"] = False
        result["failures"].append(f"expected one of {any_of} in the answer")

    # Lexical aspect coverage is a regression signal, not an entailment or
    # comprehension score. Live evaluation still requires substantive review.
    coverage = {aspect: any(term.casefold() in lowered for term in terms)
                for aspect, terms in case.get("must_cover", {}).items()}
    if coverage:
        result["aspect_mentions"] = coverage
        absent = [aspect for aspect, present in coverage.items() if not present]
        if absent:
            result["ok"] = False
            result["failures"].append(f"missing required aspect mentions: {absent}")

    if not answer.strip():
        result["ok"] = False
        result["failures"].append("empty answer")
    return result


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--secret", required=True)
    ap.add_argument("--user-id", type=int, default=1)
    ap.add_argument("--course-id", type=int)
    ap.add_argument("--case-id", action="append", help="Run only selected case IDs")
    args = ap.parse_args()

    cases = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    if args.case_id:
        cases = [case for case in cases if case["id"] in args.case_id]
        if not cases:
            ap.error("No matching case IDs")
    else:
        cases = [case for case in cases if not case.get("opt_in")]
    if args.course_id is not None and args.course_id <= 0:
        ap.error("--course-id must be positive")
    if any(case.get("requires_course") for case in cases) and args.course_id is None:
        ap.error("Selected cases require --course-id for an authorized course")
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for case in cases:
            res = await run_case(client, args.base_url, args.secret, args.user_id, case, args.course_id)
            results.append(res)
            status = "PASS" if res["ok"] else "FAIL"
            print(f"[{status}] {res['id']} model={res['model']} refs={len(res['references'])}")
            if res.get("retrieval_evidence"):
                print(f"       evidence={json.dumps(res['retrieval_evidence'], sort_keys=True)} latency={res['elapsed_seconds']}s")
            for failure in res["failures"]:
                print(f"       - {failure}")

    passed = sum(1 for r in results if r["ok"])
    print(f"\n{passed}/{len(results)} golden cases passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
