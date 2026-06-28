"""
Mentor Tool: create_mini_challenge

Creates a short interactive quiz question directly from LLM.
NOT saved to the main quiz database - this is ephemeral,
used for real-time learning interaction within the chat.
"""
from __future__ import annotations

import logging

from app.agents.tools.base_tool import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class CreateMiniChallengeTool(BaseTool):
    name = "create_mini_challenge"
    description = (
        "Create a short interactive quiz question for the student to "
        "practice a concept. The question is NOT saved to the database - "
        "it's ephemeral and used for in-chat learning. Use when guiding "
        "students through a topic and you want to test their understanding "
        "with a quick exercise."
    )
    parameters = {
        "type": "object",
        "properties": {
            "concept": {
                "type": "string",
                "description": "The specific concept to test.",
            },
            "question_type": {
                "type": "string",
                "enum": ["multiple_choice", "fill_in_blank", "true_false",
                         "short_answer"],
                "description": "Type of question. Default: multiple_choice.",
                "default": "multiple_choice",
            },
            "difficulty": {
                "type": "string",
                "enum": ["easy", "medium", "hard"],
                "description": "Difficulty level.",
                "default": "medium",
            },
            "language": {
                "type": "string",
                "enum": ["vi", "en"],
                "default": "vi",
            },
            "course_id": {
                "type": "integer",
                "description": "Optional course ID for RAG context.",
            },
        },
        "required": ["concept"],
    }

    async def execute(self, **kwargs) -> ToolResult:
        from app.core.llm import chat_complete_json
        from app.core.llm_gateway import TASK_QUIZ_GEN

        concept = kwargs["concept"]
        q_type = kwargs.get("question_type", "multiple_choice")
        difficulty = kwargs.get("difficulty", "medium")
        language = kwargs.get("language", "vi")
        course_id = kwargs.get("course_id")

        try:
            # Optional: get RAG context for better questions
            context = ""
            if course_id:
                from app.services.rag_service import rag_service
                chunks = await rag_service.search_multilingual(
                    query=concept, course_id=course_id, top_k=2,
                )
                if chunks:
                    context = "\n".join(c.chunk_text for c in chunks)

            lang_note = "Viết bằng tiếng Việt." if language == "vi" else "Write in English."

            type_instructions = {
                "multiple_choice": (
                    "Create a multiple-choice question with exactly 4 options (A, B, C, D). "
                    "Only one option should be correct."
                ),
                "fill_in_blank": (
                    "Create a fill-in-the-blank question. Use ___ to mark the blank. "
                    "Provide the correct answer."
                ),
                "true_false": (
                    "Create a true/false statement. Include a brief explanation."
                ),
                "short_answer": (
                    "Create a short-answer question that can be answered in 1-2 sentences."
                ),
            }

            system_prompt = (
                f"You are a quiz creator for educational purposes. {lang_note}\n"
                f"Difficulty: {difficulty}\n"
                f"{type_instructions.get(q_type, type_instructions['multiple_choice'])}\n\n"
                f"Output JSON:\n"
                f'{{"question": "string",'
                f' "options": ["A. ...", "B. ...", "C. ...", "D. ..."],'
                f' "correct_answer": "A",'
                f' "explanation": "string",'
                f' "hint": "string"}}\n\n'
                f"For fill_in_blank, omit 'options' and set correct_answer to the answer.\n"
                f"For true_false, options should be ['Đúng/True', 'Sai/False'].\n"
                f"For short_answer, omit 'options'.\n\n"
                + (f"CONTEXT:\n{context}" if context else "")
            )

            result = await chat_complete_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Create a {difficulty} {q_type} question about: {concept}"},
                ],
                temperature=0.7,
                max_tokens=512,
                task=TASK_QUIZ_GEN,
            )

            # Parse and format options to match the frontend MCQOption schema:
            # interface MCQOption { text: string; is_correct: boolean; explanation?: string; }
            formatted_options = []
            raw_options = result.get("options", result.get("choices", []))
            correct_ans = str(result.get("correct_answer", "")).strip()
            explanation = result.get("explanation", "")

            logger.debug(
                "create_mini_challenge raw LLM output - options=%r, correct_answer=%r",
                raw_options, correct_ans,
            )

            if not raw_options and q_type in ["multiple_choice", "true_false"]:
                if q_type == "true_false":
                    raw_options = ["Đúng/True", "Sai/False"]
                else:
                    raw_options = []

            for idx, opt in enumerate(raw_options):
                option_char = chr(65 + idx)  # 'A', 'B', 'C', 'D'
                option_char_lower = option_char.lower()
                opt_text = ""
                is_correct = False
                opt_explanation = ""

                # ── Extract text & correctness from diverse LLM schemas ──
                if isinstance(opt, dict):
                    # Try many key variations LLMs use
                    for key in ("text", "option", "content", "label",
                                "value", "answer", "option_text"):
                        val = opt.get(key)
                        if val and str(val).strip():
                            opt_text = str(val).strip()
                            break
                    # If still empty, grab the first non-empty string value
                    if not opt_text:
                        for v in opt.values():
                            if isinstance(v, str) and v.strip():
                                opt_text = v.strip()
                                break
                    # Correctness from dict
                    is_correct = bool(
                        opt.get("is_correct",
                        opt.get("correct",
                        opt.get("isCorrect", False)))
                    )
                    if not is_correct:
                        # Fallback: check if the key of the dict corresponds to option_char
                        for k in opt.keys():
                            if str(k).upper().strip() == option_char:
                                if correct_ans.upper().strip() == option_char:
                                    is_correct = True
                    opt_explanation = opt.get(
                        "explanation", explanation if is_correct else ""
                    )
                else:
                    opt_text = str(opt).strip()
                    # Match correct_answer against the option letter
                    correct_clean = correct_ans.upper().strip()
                    if correct_clean == option_char:
                        is_correct = True
                    elif (
                        len(correct_clean) > 1
                        and correct_clean[0] == option_char
                        and correct_clean[1] in (".", ")", ":", " ")
                    ):
                        is_correct = True
                    elif correct_ans.strip().lower() == opt_text.lower():
                        is_correct = True
                    elif (
                        len(correct_ans) > 3
                        and correct_ans.lower() in opt_text.lower()
                    ):
                        is_correct = True
                    opt_explanation = explanation if is_correct else ""

                # ── Strip option prefix (case-insensitive) ──
                # Handles "A. text", "a) text", "A: text", "A text", etc.
                raw_before_strip = opt_text
                prefix_stripped = False
                for ch in (option_char, option_char_lower):
                    for sep in (". ", ") ", ": ", " "):
                        prefix = f"{ch}{sep}"
                        if opt_text.startswith(prefix):
                            opt_text = opt_text[len(prefix):]
                            prefix_stripped = True
                            break
                    if prefix_stripped:
                        break
                    
                    # Also handle case where it is just the prefix without a trailing space/text, e.g. "B.", "B:", "B)", "B"
                    for sep in (".", ")", ":", ""):
                        prefix = f"{ch}{sep}"
                        if opt_text.strip() == prefix:
                            opt_text = ""
                            prefix_stripped = True
                            break
                    if prefix_stripped:
                        break

                # ── Fallback: never produce empty or placeholder-only text ──
                stripped = opt_text.strip()
                if not stripped or stripped in ("...", "…", "___"):
                    # Check if raw_before_strip is just prefix or placeholder
                    raw_clean = raw_before_strip.strip()
                    is_only_prefix = False
                    for ch in (option_char, option_char_lower):
                        if raw_clean in (ch, f"{ch}.", f"{ch})", f"{ch}:"):
                            is_only_prefix = True
                            break
                    if not raw_clean or raw_clean in ("...", "…", "___") or is_only_prefix:
                        opt_text = f"Option {option_char}"
                    else:
                        opt_text = raw_clean

                formatted_options.append({
                    "text": opt_text.strip(),
                    "is_correct": is_correct,
                    "explanation": opt_explanation,
                })

            logger.debug(
                "create_mini_challenge formatted_options=%r", formatted_options,
            )

            return ToolResult(
                status="success",
                data={
                    "challenge": result,
                    "concept": concept,
                    "question_type": q_type,
                    "difficulty": difficulty,
                },
                message=f"Đây là một bài tập nhỏ về '{concept}'!",
                ui_instruction={
                    "component": "MiniChallengeWidget",
                    "props": {
                        "question": result.get("question", ""),
                        "options": formatted_options,
                        "concept": concept,
                    },
                },
            )


        except Exception as e:
            logger.error("create_mini_challenge failed: %s", e)
            return ToolResult(
                status="error",
                data={"error": str(e)},
                message=f"Lỗi tạo bài tập: {e}",
            )
