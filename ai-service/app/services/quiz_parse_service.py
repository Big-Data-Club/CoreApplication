"""
ai-service/app/services/quiz_parse_service.py

QuizParseService: Accepts raw, unformatted text (copy-pasted from textbooks,
exam papers, websites, etc.) and uses an LLM to extract structured quiz
questions without requiring any fixed input format.

Supported question types detected automatically:
  - SINGLE_CHOICE   : One correct answer from multiple options
  - MULTIPLE_CHOICE : Multiple correct answers
  - FILL_BLANK_TEXT : Fill-in-the-blank with text answers
  - SHORT_ANSWER    : Short free-text answer (no blanks)
  - ESSAY           : Long-form open answer

Usage:
    from app.services.quiz_parse_service import quiz_parse_service
    result = await quiz_parse_service.parse(raw_text, language="vi")
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.llm import chat_complete_json
from app.core.llm_gateway import TASK_QUIZ_GEN

logger = logging.getLogger(__name__)


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an expert at parsing quiz questions from unstructured text.
The text may come from: exam papers, textbooks, websites, PDFs, Word docs, or free-form notes.
The text may be in ANY language (Vietnamese, English, etc.).

Your job is to extract ALL quiz questions from the input and return a structured JSON list.

Supported question types:
- SINGLE_CHOICE: Multiple options, exactly one is correct. Options may be numbered (1,2,3...), lettered (A,B,C...), or bulleted.
- MULTIPLE_CHOICE: Multiple options, more than one can be correct. Usually says "select all that apply" or similar.
- FILL_BLANK_TEXT: Sentence with blanks to fill in. Blanks may appear as "...", "___", "{}", numbered blanks, or the text explicitly says fill in the blank.
- SHORT_ANSWER: Open question with a definite short answer (e.g., a word, number, command).
- ESSAY: Open-ended question requiring a long explanation.

Return a JSON array. Each element must have exactly this structure:
{
  "question_type": "SINGLE_CHOICE" | "MULTIPLE_CHOICE" | "FILL_BLANK_TEXT" | "SHORT_ANSWER" | "ESSAY",
  "question_text": "the question or sentence to fill in. For FILL_BLANK_TEXT: replace blanks with {BLANK_1}, {BLANK_2}, etc.",
  "points": 10,
  "answer_options": [
    {"option_text": "...", "is_correct": true|false}
  ],
  "correct_answers": [
    {"answer_text": "...", "blank_id": 1, "case_sensitive": false, "exact_match": false}
  ],
  "settings": null,
  "explanation": "optional explanation hint"
}

Rules:
1. For SINGLE_CHOICE and MULTIPLE_CHOICE:
   - List ALL options in answer_options.
   - Mark is_correct=true for the correct option(s).
   - Look for hints like "It's a very ...", italics, or notes after options to identify the correct answer.
   - correct_answers must be [].

2. For FILL_BLANK_TEXT:
   - Replace EACH blank with {BLANK_1}, {BLANK_2}, etc. in question_text.
   - correct_answers: one entry per blank with blank_id matching the number.
   - Extract the correct answer text from the surrounding context (e.g., after the sentence, in parentheses, numbered answers, etc.).
   - answer_options must be [].
   - settings = {"blank_count": N, "blanks": [{"blank_id": 1}, {"blank_id": 2}, ...]}

3. For SHORT_ANSWER:
   - correct_answers has the expected answer(s).
   - answer_options must be [].

4. For ESSAY:
   - Both answer_options and correct_answers are [].

5. Parse ALL questions present in the text, even if format differs between questions.
6. Do NOT include explanatory text or footnotes as questions.
7. Return ONLY valid JSON. No markdown, no explanation outside JSON.
"""

_USER_TEMPLATE = """Parse the following text and extract all quiz questions as a JSON array.
Text language may be mixed — preserve the original language in question_text and options.

TEXT TO PARSE:
---
{raw_text}
---

Return only the JSON array of question objects. No extra text."""


# ── Service ───────────────────────────────────────────────────────────────────

class QuizParseService:
    """Parse raw text into structured quiz question dicts via LLM."""

    async def parse(
        self,
        raw_text: str,
        points_per_question: int = 10,
        language: str = "vi",
    ) -> list[dict[str, Any]]:
        """
        Parse raw unformatted text into a list of structured question dicts
        ready to be batch-inserted via quizService.createQuestionsBatch().

        Returns list of dicts with keys:
            question_type, question_text, points, answer_options,
            correct_answers, settings, explanation
        """
        if not raw_text or not raw_text.strip():
            return []

        user_msg = _USER_TEMPLATE.format(raw_text=raw_text.strip())

        try:
            raw_json = await chat_complete_json(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_msg},
                ],
                temperature=0.1,
                task=TASK_QUIZ_GEN,
            )
        except Exception as exc:
            logger.error("LLM quiz parse failed: %s", exc)
            raise

        questions = self._normalize(raw_json, points_per_question)
        logger.info("quiz_parse_service: parsed %d questions from %d chars of text",
                    len(questions), len(raw_text))
        return questions

    # ── Private helpers ───────────────────────────────────────────────────────

    def _normalize(self, raw: Any, points_per_question: int) -> list[dict]:
        """Ensure output is a list of valid question dicts."""
        # LLM may return a dict with a list key, or the list directly
        if isinstance(raw, dict):
            for key in ("questions", "items", "data", "result"):
                if isinstance(raw.get(key), list):
                    raw = raw[key]
                    break
            else:
                raw = list(raw.values())[0] if raw else []

        if not isinstance(raw, list):
            logger.warning("quiz_parse_service: unexpected LLM output type: %s", type(raw))
            return []

        normalized = []
        for i, q in enumerate(raw):
            if not isinstance(q, dict):
                continue
            normalized.append(self._normalize_question(q, i, points_per_question))

        return normalized

    def _normalize_question(self, q: dict, index: int, points: int) -> dict:
        """Normalize a single question dict to the LMS expected format."""
        qtype = q.get("question_type", "SINGLE_CHOICE").upper()
        valid_types = {
            "SINGLE_CHOICE", "MULTIPLE_CHOICE", "FILL_BLANK_TEXT",
            "FILL_BLANK_DROPDOWN", "SHORT_ANSWER", "ESSAY", "FILE_UPLOAD",
        }
        if qtype not in valid_types:
            qtype = "SINGLE_CHOICE"

        question_text = str(q.get("question_text", "")).strip()

        # Normalize answer_options
        raw_opts = q.get("answer_options") or []
        if not isinstance(raw_opts, list):
            raw_opts = []
        answer_options = []
        for j, opt in enumerate(raw_opts):
            if isinstance(opt, dict):
                answer_options.append({
                    "option_text": str(opt.get("option_text", opt.get("text", ""))).strip(),
                    "is_correct": bool(opt.get("is_correct", False)),
                    "order_index": j + 1,
                })

        # Normalize correct_answers
        raw_answers = q.get("correct_answers") or []
        if not isinstance(raw_answers, list):
            raw_answers = []
        correct_answers = []
        for ans in raw_answers:
            if isinstance(ans, dict):
                correct_answers.append({
                    "answer_text": str(ans.get("answer_text", "")).strip(),
                    "blank_id":    ans.get("blank_id"),
                    "case_sensitive": bool(ans.get("case_sensitive", False)),
                    "exact_match":    bool(ans.get("exact_match", False)),
                })
            elif isinstance(ans, str):
                correct_answers.append({
                    "answer_text": ans.strip(),
                    "case_sensitive": False,
                    "exact_match": False,
                })

        # Build FILL_BLANK_TEXT settings from correct_answers
        settings = q.get("settings")
        if qtype == "FILL_BLANK_TEXT" and not settings:
            blank_ids = sorted({
                a["blank_id"] for a in correct_answers
                if a.get("blank_id") is not None
            })
            if not blank_ids:
                # Infer blanks from {BLANK_N} in question_text
                blank_ids = [int(m) for m in re.findall(r"\{BLANK_(\d+)\}", question_text)]
            settings = {
                "blank_count": len(blank_ids),
                "blanks": [{"blank_id": bid} for bid in blank_ids],
            }
            # Ensure blank_ids are set on correct_answers
            if correct_answers and blank_ids and not correct_answers[0].get("blank_id"):
                for k, ans in enumerate(correct_answers):
                    ans["blank_id"] = blank_ids[k] if k < len(blank_ids) else k + 1

        return {
            "question_type":  qtype,
            "question_text":  question_text,
            "points":         int(q.get("points", points)),
            "order_index":    index + 1,
            "explanation":    str(q.get("explanation", "")).strip(),
            "answer_options": answer_options,
            "correct_answers": correct_answers,
            "settings":       settings,
            "is_required":    True,
        }


quiz_parse_service = QuizParseService()
