"""
Golden-QA evaluation harness for the BDC agent.

Runs a set of golden questions against a LIVE ai-service and scores the
verifiability contract:

  1. grounding   - cases marked expected_sources=true must return
                   DONE.references with >=1 entry.
  2. no-fabrication - every inline [n] marker in the answer must map to an
                   existing reference (no dangling citations).
  3. relevance   - answer must contain the configured keywords (casefold).

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
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agents.core.references import validate_inline_citations  # noqa: E402

GOLDEN_FILE = Path(__file__).resolve().parents[1] / "eval" / "golden_qa.json"


async def run_case(client: httpx.AsyncClient, base_url: str, secret: str,
                   user_id: int, case: dict) -> dict[str, Any]:
    payload = {
        "message": case["message"],
        "agent_type": case.get("agent", "mentor"),
        "user_id": user_id,
        "page_context": {"pageType": case.get("pageType", "other")},
    }
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

    answer = "".join(text_parts)
    result["text"] = answer
    result["references"] = [r.get("title") for r in references]

    # 1. Grounding
    if case.get("expected_sources") and not references:
        result["ok"] = False
        result["failures"].append("expected sources but DONE.references was empty")

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

    if not answer.strip():
        result["ok"] = False
        result["failures"].append("empty answer")
    return result


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--secret", required=True)
    ap.add_argument("--user-id", type=int, default=1)
    args = ap.parse_args()

    cases = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient() as client:
        for case in cases:
            res = await run_case(client, args.base_url, args.secret, args.user_id, case)
            results.append(res)
            status = "PASS" if res["ok"] else "FAIL"
            print(f"[{status}] {res['id']} model={res['model']} refs={len(res['references'])}")
            for failure in res["failures"]:
                print(f"       - {failure}")

    passed = sum(1 for r in results if r["ok"])
    print(f"\n{passed}/{len(results)} golden cases passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
