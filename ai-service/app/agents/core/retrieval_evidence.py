"""Per-turn evidence accounting and balanced context across retrieval calls.

These are observable source counts, not measures of model comprehension.
Original tool results remain in the caller's history; pooling affects private
request copies only. Every source remains untrusted data under its original ref.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field

RETRIEVAL_TOOLS = frozenset({"search_course_materials", "explain_concept", "search_web", "fetch_page"})


def source_key(row: dict) -> str:
    if row.get("chunk_id"):
        return f"chunk:{row.get('content_id')}:{row['chunk_id']}"
    text = row.get("child_text") or row.get("text") or row.get("snippet") or ""
    return json.dumps([row.get("url"), row.get("content_id"), row.get("page_number"),
                       " ".join(str(text).split())], ensure_ascii=False)


def evidence_rows(data: dict) -> list[dict]:
    rows = data.get("chunks") or data.get("results") or []
    if not rows and data.get("content"):
        rows = [{"text": data["content"], "url": data.get("url"), "ref": data.get("ref")}]
    return [row for row in rows if isinstance(row, dict) and
            isinstance(row.get("child_text") or row.get("text") or row.get("snippet"), str)]


def cited_refs(text: str) -> set[int]:
    text = re.sub(r"```[\s\S]*?```|`[^`]*`", "", text or "")
    return {int(m.group(1)) for m in re.finditer(r"\[(?:ref\s*)?(\d+)\]", text, re.I)}


def _score(row: dict) -> float:
    value = row.get("similarity", row.get("relevance_score", 0))
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else 0.0


def pool_retrieval_evidence(messages: list[dict]) -> list[dict]:
    """Merge authorized retrieval data while preserving every tool-call reply.

    Round-robin ranked query groups so early and later searches both contribute.
    Other tools, failed reads, conversation recall and write results are untouched.
    """
    groups: list[tuple[int, dict, list[dict]]] = []
    for index, message in enumerate(messages):
        if message.get("role") != "tool" or not isinstance(message.get("content"), str):
            continue
        try:
            payload = json.loads(message["content"])
        except (ValueError, TypeError):
            continue
        if not isinstance(payload, dict) or payload.get("status") != "success":
            continue
        provenance = payload.get("evidence") or {}
        data = payload.get("data")
        if not isinstance(provenance, dict) or provenance.get("source") not in RETRIEVAL_TOOLS or not isinstance(data, dict):
            continue
        rows = evidence_rows(data)
        if rows:
            groups.append((index, payload, sorted(rows, key=_score, reverse=True)))
    if len(groups) < 2:
        return messages

    seen, pooled = set(), []
    for rank in range(max(len(rows) for _, _, rows in groups)):
        for _, payload, rows in groups:
            if rank >= len(rows):
                continue
            row = rows[rank]
            key = source_key(row)
            if key in seen:
                continue
            seen.add(key)
            # Keep source IDs and exact excerpts; no generated facts are added.
            item = {k: row[k] for k in ("ref", "chunk_id", "content_id", "page_number", "url") if row.get(k) is not None}
            item["text"] = row.get("child_text") or row.get("text") or row.get("snippet")
            if row.get("reader_aspects"):
                item["reader_aspects"] = row["reader_aspects"]
            if row.get("child_text") or row.get("_excerpted"):
                item["_excerpted"] = True
            pooled.append(item)

    packed = [dict(message) for message in messages]
    for index, payload, rows in groups:
        packed[index]["content"] = json.dumps({
            "status": "success", "data": {"refs": [r["ref"] for r in rows if r.get("ref")]},
            "message": "Source excerpts are retained in the accumulated retrieval evidence below.",
            "evidence": payload["evidence"],
        }, ensure_ascii=False)
    pooled_data = {"chunks": pooled, "unique_sources": len(pooled)}
    gap_report = groups[-1][1]["data"].get("reader_suggested_gaps")
    if isinstance(gap_report, dict):
        pooled_data["reader_suggested_gaps"] = gap_report
    packed[groups[-1][0]]["content"] = json.dumps({
        "status": "success", "data": pooled_data,
        "message": "Accumulated evidence across retrieval calls, not just the latest search. Each ref retains its original source.",
        "evidence": {"source": "retrieval_workspace", "trust": "untrusted_source_data"},
    }, ensure_ascii=False)
    return packed


@dataclass
class EvidenceProgress:
    calls: int = 0
    received: int = 0
    last_added: int = 0
    stagnant_calls: int = 0
    _sources: dict[str, dict] = field(default_factory=dict)
    _refs: set[int] = field(default_factory=set)
    _prepared: set[int] = field(default_factory=set)
    _excerpted: set[int] = field(default_factory=set)
    reader_notes: dict[int, list[dict]] = field(default_factory=dict)
    reader_report: dict = field(default_factory=dict)
    reader_gaps: list[str] = field(default_factory=list)

    @property
    def sources(self) -> list[dict]:
        return list(self._sources.values())

    def observe(self, tool: str, data: dict) -> dict:
        if tool not in RETRIEVAL_TOOLS:
            return {}
        rows = evidence_rows(data)
        self.calls += 1
        self.received += len(rows)
        before = len(self._sources)
        for row in rows:
            self._sources.setdefault(source_key(row), dict(row))
        self._refs.update(row["ref"] for row in rows if type(row.get("ref")) is int)
        self.last_added = len(self._sources) - before
        self.stagnant_calls = self.stagnant_calls + 1 if not self.last_added else 0
        return {"unique_sources": len(self._sources), "new_sources": self.last_added,
                "consecutive_no_gain": self.stagnant_calls}

    def prepared(self, messages: list[dict]) -> None:
        refs, excerpted = set(), set()
        for message in messages:
            if message.get("role") != "tool":
                continue
            try:
                payload = json.loads(message.get("content", ""))
            except (ValueError, TypeError):
                continue
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
                continue
            provenance = payload.get("evidence") or {}
            if not isinstance(provenance, dict) or provenance.get("source") not in RETRIEVAL_TOOLS | {"retrieval_workspace"}:
                continue
            for row in evidence_rows(payload["data"]):
                ref = row.get("ref")
                if type(ref) is int:
                    refs.add(ref)
                    if row.get("_excerpted"):
                        excerpted.add(ref)
        self._prepared, self._excerpted = refs, excerpted

    def snapshot(self, answer: str = "") -> dict:
        return {"retrieval_calls": self.calls, "received_entries": self.received,
                "unique_sources": len(self._sources), "prepared_sources": len(self._prepared & self._refs),
                "excerpted_sources": len(self._excerpted & self._refs),
                "cited_sources": len(cited_refs(answer) & self._refs),
                "last_added_sources": self.last_added, "no_gain_calls": self.stagnant_calls,
                **self.reader_report}
