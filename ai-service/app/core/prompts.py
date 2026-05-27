"""System prompts and prompt builders for the AI service.
Extracted from app.core.llm so the call mechanics and the prompt content live
in separate modules. All public names are re-exported from app.core.llm for
backward compatibility.
"""
from __future__ import annotations
import json
SYSTEM_PROMPT_TUTOR = {
    "vi": (
        "You are an AI tutor that analyzes student errors based on official course materials. "
        "The materials may be in English or Vietnamese — read and understand them, then write the explanation in Vietnamese. "
        "Always base your response strictly on the provided documents without hallucination. "
        "Return ONLY valid JSON, with no extra conversational text or markdown wrappers."
    ),
    "en": (
        "You are an AI tutor that diagnoses student errors based on official course materials. "
        "The materials may be in Vietnamese or English — read and understand them, then write the explanation in English. "
        "Always base your response strictly on the provided documents without hallucination. "
        "Return ONLY valid JSON, with no extra conversational text or markdown wrappers."
    ),
}
SYSTEM_PROMPT_QUIZ_GEN = {
    "vi": (
        "You are an expert assessment designer using Bloom's Taxonomy. "
        "The system supports full Markdown (bold, italic, tables, lists), code blocks, "
        "and KaTeX math formulas ($...$ for inline and $$...$$ for block). "
        "Use Markdown intelligently to make the questions clear and professional, but do not abuse it. "
        "The source materials may be in English or Vietnamese — read and understand them, "
        "then generate the questions, options, and explanations in Vietnamese. "
        "Return ONLY valid JSON matching the requested schema exactly, with no extra conversational text or markdown wrappers."
    ),
    "en": (
        "You are an expert at designing assessments following Bloom's Taxonomy. "
        "The system supports full Markdown (bold, italic, tables, lists), code blocks, "
        "and KaTeX math formulas ($...$ for inline and $$...$$ for block). "
        "Use Markdown intelligently to enhance clarity, but do not overuse it. "
        "The source materials may be in Vietnamese or English — read and understand them, "
        "then generate the questions, options, and explanations in English. "
        "Return ONLY valid JSON matching the requested schema exactly, with no extra conversational text or markdown wrappers."
    ),
}
SYSTEM_PROMPT_FLASHCARD_GEN = {
    "vi": (
        "You are an expert at creating study flashcards for Spaced Repetition. "
        "The source materials may be in English or Vietnamese — read and understand them, "
        "then generate the flashcards (front and back text) in Vietnamese. "
        "Return ONLY valid JSON matching the requested schema exactly, with no extra conversational text or markdown wrappers."
    ),
    "en": (
        "You are an expert at creating study flashcards for Spaced Repetition. "
        "The source materials may be in Vietnamese or English — read and understand them, "
        "then generate the flashcards (front and back text) in English. "
        "Return ONLY valid JSON matching the requested schema exactly, with no extra conversational text or markdown wrappers."
    ),
}
# ── Diagnosis ──────────────────────────────────────────────────────────────
_DIAGNOSIS_FEW_SHOT_VI = [
    {
        "role": "user",
        "content": (
            "TÀI LIỆU THAM KHẢO:\n"
            "[Đoạn 1] Đa hình (Polymorphism) là khả năng một phương thức hoạt động "
            "khác nhau tùy đối tượng gọi. Java thực hiện qua method overriding.\n\n"
            "---\n"
            "CÂU HỎI: Đâu là ví dụ đúng về đa hình trong Java?\n"
            "ĐÁP ÁN ĐÚNG: Lớp con override phương thức của lớp cha\n"
            "CÁC ĐÁP ÁN NHIỄU:\n  - Gọi constructor của lớp cha\n  - Dùng biến static\n"
            "HỌC SINH TRẢ LỜI: Gọi constructor của lớp cha\n\n"
            "Phân tích tại sao sai. Trả về JSON."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "explanation": (
                "Học sinh nhầm kế thừa với đa hình. "
                "Constructor không bị override — đa hình xảy ra khi lớp con "
                "cung cấp phiên bản mới của một instance method từ lớp cha."
            ),
            "gap_type": "misconception",
            "knowledge_gap": "Không phân biệt constructor, static method và instance method override trong đa hình",
            "study_suggestion": "Xem lại Đoạn 1, thực hành viết class Animal với speak() bị override bởi Dog và Cat",
            "confidence": 0.87,
            "relevant_source_indices": [1],
        }, ensure_ascii=False),
    },
]
_DIAGNOSIS_FEW_SHOT_EN = [
    {
        "role": "user",
        "content": (
            "REFERENCE MATERIAL:\n"
            "[Segment 1] Polymorphism allows a method to behave differently "
            "depending on the calling object. In Java this is done via method overriding.\n\n"
            "---\n"
            "QUESTION: Which is a correct example of polymorphism in Java?\n"
            "CORRECT ANSWER: A subclass overrides a superclass method\n"
            "DISTRACTORS:\n  - Calling a parent constructor\n  - Using static variables\n"
            "STUDENT ANSWERED: Calling a parent constructor\n\n"
            "Analyse why the student chose wrongly. Return JSON."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "explanation": (
                "The student confused inheritance with polymorphism. "
                "Constructors are not overridden — polymorphism occurs when a subclass "
                "provides a new implementation of an instance method."
            ),
            "gap_type": "misconception",
            "knowledge_gap": "Cannot distinguish constructor, static method, and instance method overriding in the context of polymorphism",
            "study_suggestion": "Re-read Segment 1. Practice writing an Animal class with speak() overridden by Dog and Cat.",
            "confidence": 0.87,
            "relevant_source_indices": [1],
        }),
    },
]
def build_diagnosis_prompt(
    question_text: str,
    wrong_answer: str,
    correct_answer: str,
    distractor_options: list[str],
    context_chunks: list[str],
    language: str = "vi",
) -> list[dict]:
    lang_name = "Vietnamese" if language == "vi" else "English"
    context = "\n---\n".join(f"[Segment {i+1}] {c}" for i, c in enumerate(context_chunks))
    distractors = "\n".join(f"  - {d}" for d in distractor_options) if distractor_options else "None"
    
    user_msg = (
        f"REFERENCE MATERIAL:\n{context}\n\n"
        f"NOTE: Source materials may be in English or Vietnamese. Read them and write the response in {lang_name}.\n---\n"
        f"QUESTION: {question_text}\n"
        f"CORRECT ANSWER: {correct_answer}\n"
        f"DISTRACTORS:\n{distractors}\n"
        f"STUDENT ANSWERED: {wrong_answer}\n\n"
        f"TASK: Analyze WHY the student chose the wrong answer \"{wrong_answer}\" instead of the correct answer.\n"
        f"Return the analysis as a JSON object matching the schema below. "
        f"All text fields ('explanation', 'knowledge_gap', 'study_suggestion') MUST be written in {lang_name}.\n"
        f"The 'relevant_source_indices' should contain the 1-based segment indices from the reference materials that are actually relevant to diagnosing the misconception (or [] if none).\n\n"
        f"REQUIRED JSON SCHEMA:\n"
        f'{{"explanation":"Detailed analysis of student error in {lang_name}",'
        f'"gap_type":"misconception|missing_prerequisite|careless|other",'
        f'"knowledge_gap":"Specific concept the student is missing or misunderstood in {lang_name}",'
        f'"study_suggestion":"Actionable study recommendation referencing the relevant segments in {lang_name}",'
        f'"confidence":0.0,'
        f'"relevant_source_indices":[1]}}'
    )
    few_shot = _DIAGNOSIS_FEW_SHOT_VI if language == "vi" else _DIAGNOSIS_FEW_SHOT_EN
    return [
        {"role": "system", "content": SYSTEM_PROMPT_TUTOR[language]},
        *few_shot,
        {"role": "user", "content": user_msg},
    ]
# ── Quiz generation ────────────────────────────────────────────────────────
_QUIZ_FEW_SHOT_VI = [
    {
        "role": "user",
        "content": (
            "TÀI LIỆU:\n[Nguồn 1] Định luật bảo toàn năng lượng: $E = K + U = \\text{const}$. "
            "Trong đó $K$ là động năng, $U$ là thế năng.\n\n"
            "CHỦ ĐỀ: Năng lượng\nCẤP ĐỘ BLOOM: Nhớ (remember)\n"
            "Tạo 1 câu hỏi trắc nghiệm. Trả về JSON."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "question_text": "Công thức nào sau đây biểu diễn **Định luật bảo toàn cơ năng**?",
            "bloom_level": "remember",
            "question_type": "SINGLE_CHOICE",
            "answer_options": [
                {"text": "$E = K + U = \\text{const}$", "is_correct": True,  "explanation": "Tổng động năng và thế năng là một hằng số trong hệ kín."},
                {"text": "$F = ma$",                  "is_correct": False, "explanation": "Đây là Định luật II Newton."},
                {"text": "$E = mc^2$",                 "is_correct": False, "explanation": "Đây là công thức tương quan năng lượng - khối lượng của Einstein."},
                {"text": "$P = IV$",                   "is_correct": False, "explanation": "Đây là công thức tính công suất điện."},
            ],
            "explanation": "Cơ năng toàn phần $E$ là tổng của động năng $K$ và thế năng $U$.",
            "source_quote": "Định luật bảo toàn năng lượng: $E = K + U = \\text{const}$",
        }, ensure_ascii=False),
    },
]
_QUIZ_FEW_SHOT_EN = [
    {
        "role": "user",
        "content": (
            "MATERIAL:\n[Source 1] The `map()` function in Python creates an iterator that computes the function using local arguments.\n\n"
            "TOPIC: Python Functions\nBLOOM LEVEL: Apply\n"
            "Create 1 multiple choice question. Return JSON."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "question_text": "Given the list `nums = [1, 2, 3]`, which code snippet correctly uses `map()` to square each number?",
            "bloom_level": "apply",
            "question_type": "SINGLE_CHOICE",
            "answer_options": [
                {"text": "`map(lambda x: x**2, nums)`", "is_correct": True,  "explanation": "This correctly applies a squaring function to the list via map."},
                {"text": "`nums.map(x => x**2)`",       "is_correct": False, "explanation": "This is JavaScript syntax, not Python."},
                {"text": "`map(nums, x**2)`",          "is_correct": False, "explanation": "The function must be the first argument in `map()`."},
                {"text": "`[x**2 for x in nums]`",      "is_correct": False, "explanation": "While this squares numbers, it uses list comprehension, not the `map()` function."},
            ],
            "explanation": "The `map(function, iterable)` syntax is standard for applying a transformation across an iterator in Python.",
            "source_quote": "The `map()` function in Python creates an iterator",
        }),
    },
]
def build_quiz_generation_prompt(
    bloom_level: str,
    context_chunks: list[str],
    node_name: str,
    language: str = "vi",
    existing_questions: list[str] | None = None,
) -> list[dict]:
    lang_name = "Vietnamese" if language == "vi" else "English"
    context = "\n---\n".join(f"[Source {i+1}] {c}" for i, c in enumerate(context_chunks))
    existing = (
        "\n\nAVOID DUPLICATING THE FOLLOWING EXISTING QUESTIONS:\n" + "\n".join(f"- {q}" for q in existing_questions[:5])
        if existing_questions else ""
    )
    bloom_desc = {
        "remember":   "Remember",
        "understand": "Understand",
        "apply":      "Apply",
        "analyze":    "Analyze",
        "evaluate":   "Evaluate",
        "create":     "Create",
    }
    bloom_lbl = bloom_desc.get(bloom_level, "Remember")
    schema = (
        '{"question_text":"...","bloom_level":"' + bloom_level + '",'
        '"question_type":"SINGLE_CHOICE",'
        '"answer_options":['
        '{"text":"...","is_correct":true,"explanation":"..."},'
        '{"text":"...","is_correct":false,"explanation":"..."},'
        '{"text":"...","is_correct":false,"explanation":"..."},'
        '{"text":"...","is_correct":false,"explanation":"..."}'
        '],"explanation":"...","source_quote":"..."}'
    )
    
    design_notes = (
        f"DESIGN NOTES:\n"
        f"1. Source materials may be in English or Vietnamese. Write the question, options, and explanations in {lang_name}.\n"
        f"2. Use Markdown (**bold**, `code`, $math$, $$math block$$) smartly for a professional feel.\n"
        f"3. ANTI-BIAS: Ensure distractors are plausible and relevant. Question must be objective.\n"
        f"4. INTELLIGENCE: The question must require reasoning based on the provided source material from the Knowledge Base."
    )
    
    user_msg = (
        f"MATERIAL (From Vector DB/Graph):\n{context}{existing}\n\n{design_notes}\n\n"
        f"TOPIC: {node_name}\n"
        f"BLOOM LEVEL: {bloom_lbl} ({bloom_level})\n\n"
        f"Create 1 high-quality multiple choice question in {lang_name}. Return JSON:\n{schema}"
    )
    few_shot = _QUIZ_FEW_SHOT_VI if language == "vi" else _QUIZ_FEW_SHOT_EN
    return [
        {"role": "system", "content": SYSTEM_PROMPT_QUIZ_GEN[language]},
        *few_shot,
        {"role": "user", "content": user_msg},
    ]
# ── Flashcard generation ───────────────────────────────────────────────────
_FLASHCARD_FEW_SHOT_VI = [
    {
        "role": "user",
        "content": (
            "TÀI LIỆU:\n[Nguồn 1] Cây nhị phân tìm kiếm (BST): node trái < node hiện tại < node phải.\n\n"
            "CHỦ ĐỀ: BST\nLỖI SAI: Nhầm thứ tự chèn node.\nTạo 2 flashcard. Trả về JSON."
        ),
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "flashcards": [
                {"front_text": "Quy tắc sắp xếp của BST là gì?",
                 "back_text": "Node trái < Node hiện tại < Node phải. Tất cả node bên trái nhỏ hơn, bên phải lớn hơn."},
                {"front_text": "Chèn giá trị 5 vào BST có root = 3 và node phải = 7, kết quả?",
                 "back_text": "5 trở thành con trái của 7 vì 5 > 3 (đi phải) và 5 < 7 (đi trái tại 7)."},
            ]
        }, ensure_ascii=False),
    },
]
def build_flashcard_generation_prompt(
    context_chunks: list[str],
    node_name: str,
    wrong_answers_context: str,
    count: int = 3,
    language: str = "vi",
    existing_fronts: list[str] | None = None,
) -> list[dict]:
    lang_name = "Vietnamese" if language == "vi" else "English"
    context = "\n---\n".join(f"[Source {i+1}] {c}" for i, c in enumerate(context_chunks))
    avoid = (
        "\nDO NOT DUPLICATE THESE FRONT TEXTS:\n" + "\n".join(f"- {f}" for f in (existing_fronts or [])[:10])
        if existing_fronts else ""
    )
    schema = (
        '{"flashcards":[{"front_text":"[short question/prompt]","back_text":"[short explanation/answer]"}]}'
    )
    
    lang_note = f"NOTE: Source materials may be in English or Vietnamese. Create flashcards in {lang_name}."
    user_msg = (
        f"MATERIAL:\n{context}\n\n{lang_note}\n\n"
        f"TOPIC: {node_name}\n"
        f"RECENT ERRORS:\n{wrong_answers_context}\n{avoid}\n"
        f"Create exactly {count} NEW flashcards. Return JSON matching the schema where 'front_text' and 'back_text' are in {lang_name}:\n{schema}"
    )
    few_shot = _FLASHCARD_FEW_SHOT_VI if language == "vi" else []
    return [
        {"role": "system", "content": SYSTEM_PROMPT_FLASHCARD_GEN[language]},
        *few_shot,
        {"role": "user", "content": user_msg},
    ]


# ── Concept Check (Quick Action Panel mini-quiz) ───────────────────────────
SYSTEM_PROMPT_CONCEPT_CHECK = {
    "vi": (
        "You are an expert at designing ultra-short 'Concept Check' questions for micro-lessons. "
        "Each question must test exactly ONE core concept just learned, nothing more. "
        "Questions and options must be extremely concise, preferably no longer than one line. "
        "The materials may be in English or Vietnamese — read and understand them, "
        "then write the questions, options, and explanations in Vietnamese. "
        "Return ONLY valid JSON matching the schema, with no extra conversational text or markdown wrappers."
    ),
    "en": (
        "You are an expert at designing ultra-short 'Concept Check' questions for micro-lessons. "
        "Each question must test exactly ONE core concept just learned, nothing more. "
        "Questions and options must be extremely concise, preferably no longer than one line. "
        "The materials may be in Vietnamese or English — read and understand them, "
        "then write the questions, options, and explanations in English. "
        "Return ONLY valid JSON matching the schema, with no extra conversational text or markdown wrappers."
    ),
}


def build_concept_check_prompt(
    text_chunk: str,
    node_name: str | None = None,
    count: int = 2,
    language: str = "vi",
) -> list[dict]:
    """
    Build prompt messages for the Quick Action Panel concept-check endpoint.

    The chatbot must produce 1–2 SINGLE_CHOICE multiple-choice questions
    that are answerable from ``text_chunk`` alone. Used to power the
    Quick Action Panel "Quick Check" button in the MicroLessonViewer.
    """
    lang_name = "Vietnamese" if language == "vi" else "English"
    schema = (
        '{"questions":[{'
        '"question_text":"...","question_type":"SINGLE_CHOICE",'
        '"answer_options":['
        '{"text":"...","is_correct":true,"explanation":"..."},'
        '{"text":"...","is_correct":false,"explanation":"..."},'
        '{"text":"...","is_correct":false,"explanation":"..."},'
        '{"text":"...","is_correct":false,"explanation":"..."}'
        ']}]}'
    )
    topic = node_name or ("Lesson" if language == "en" else "Bài học")
    
    user_msg = (
        f"MICRO-LESSON CONTENT:\n{text_chunk}\n\n"
        f"TOPIC: {topic}\n"
        f"Generate EXACTLY {count} SINGLE_CHOICE 'Concept Check' questions "
        f"(4 options each) grounded in the content above. "
        f"All text fields (question_text, option text, explanation) MUST be in {lang_name}.\n"
        f"Return JSON matching the schema:\n{schema}"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT_CONCEPT_CHECK[language]},
        {"role": "user", "content": user_msg},
    ]