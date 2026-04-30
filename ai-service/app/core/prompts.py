"""System prompts and prompt builders for the AI service.
Extracted from app.core.llm so the call mechanics and the prompt content live
in separate modules. All public names are re-exported from app.core.llm for
backward compatibility.
"""
from __future__ import annotations
import json
SYSTEM_PROMPT_TUTOR = {
    "vi": (
        "Bạn là gia sư AI phân tích lỗi sai của học sinh dựa trên tài liệu giảng dạy chính thức. "
        "Tài liệu có thể bằng tiếng Anh — hãy đọc hiểu và giải thích bằng tiếng Việt. "
        "Luôn dựa trên tài liệu được cung cấp, không bịa đặt. "
        "Chỉ trả về JSON hợp lệ, không thêm text hay markdown."
    ),
    "en": (
        "You are an AI tutor that diagnoses student errors based on official course materials. "
        "Materials may be in Vietnamese — read and understand them, then explain in English. "
        "Base ALL explanations on the provided documents. "
        "Return ONLY valid JSON, no extra text or markdown."
    ),
}
SYSTEM_PROMPT_QUIZ_GEN = {
    "vi": (
        "Bạn là chuyên gia thiết kế câu hỏi kiểm tra theo thang Bloom's Taxonomy. "
        "Hệ thống hỗ trợ Markdown đầy đủ (đậm, nghiêng, bảng, danh sách), khối mã (code block) "
        "và công thức toán học KaTeX ($...$ cho inline và $$...$$ cho block). "
        "Hãy sử dụng Markdown một cách thông minh để làm câu hỏi rõ ràng hơn, tuyệt đối không lạm dụng. "
        "Tài liệu có thể bằng tiếng Anh — đọc hiểu và tạo câu hỏi bằng tiếng Việt. "
        "Chỉ trả về JSON hợp lệ theo đúng schema, không thêm text khác."
    ),
    "en": (
        "You are an expert at designing assessments following Bloom's Taxonomy. "
        "The system supports full Markdown (bold, italic, tables, lists), Code Blocks, "
        "and KaTeX math formulas ($...$ for inline and $$...$$ for block). "
        "Use Markdown intelligently to enhance clarity, but do not overuse it. "
        "Source materials may be in Vietnamese — read them and create questions in English. "
        "Return ONLY valid JSON matching the requested schema exactly."
    ),
}
SYSTEM_PROMPT_FLASHCARD_GEN = {
    "vi": (
        "Bạn là chuyên gia tạo Flashcard học tập theo phương pháp Spaced Repetition. "
        "Tài liệu nguồn có thể bằng tiếng Anh — đọc hiểu và tạo flashcard bằng tiếng Việt. "
        "Chỉ trả về JSON hợp lệ theo đúng schema, không thêm text khác."
    ),
    "en": (
        "You are an expert at creating study flashcards for Spaced Repetition. "
        "Source materials may be in Vietnamese — read and understand them, create flashcards in English. "
        "Return ONLY valid JSON matching the requested schema exactly."
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
    context = "\n---\n".join(f"[Đoạn {i+1}] {c}" for i, c in enumerate(context_chunks))
    distractors = "\n".join(f"  - {d}" for d in distractor_options) if distractor_options else "Không có"
    if language == "vi":
        user_msg = (
            f"TÀI LIỆU THAM KHẢO:\n{context}\n\n"
            f"LƯU Ý: tài liệu có thể bằng tiếng Anh — đọc hiểu và giải thích bằng tiếng Việt.\n---\n"
            f"CÂU HỎI: {question_text}\n"
            f"ĐÁP ÁN ĐÚNG: {correct_answer}\n"
            f"CÁC ĐÁP ÁN NHIỄU:\n{distractors}\n"
            f"HỌC SINH TRẢ LỜI: {wrong_answer}\n\n"
            f"Phân tích TẠI SAO học sinh chọn \"{wrong_answer}\" thay vì đáp án đúng. "
            f"relevant_source_indices là mảng số thứ tự đoạn THỰC SỰ liên quan (rỗng [] nếu không có).\n"
            f'Trả về JSON: {{"explanation":"...","gap_type":"misconception|missing_prerequisite|careless|other",'
            f'"knowledge_gap":"...","study_suggestion":"...","confidence":0.0,"relevant_source_indices":[1]}}'
        )
        few_shot = _DIAGNOSIS_FEW_SHOT_VI
    else:
        context = "\n---\n".join(f"[Segment {i+1}] {c}" for i, c in enumerate(context_chunks))
        distractors = "\n".join(f"  - {d}" for d in distractor_options) if distractor_options else "None"
        user_msg = (
            f"REFERENCE MATERIAL:\n{context}\n\n"
            f"NOTE: materials may be in Vietnamese — explain in English.\n---\n"
            f"QUESTION: {question_text}\n"
            f"CORRECT ANSWER: {correct_answer}\n"
            f"DISTRACTORS:\n{distractors}\n"
            f"STUDENT ANSWERED: {wrong_answer}\n\n"
            f"Analyse WHY the student chose \"{wrong_answer}\" instead of the correct answer. "
            f"relevant_source_indices = array of segment indices actually relevant to the misconception "
            f"(return [] if none).\n"
            f'Return JSON: {{"explanation":"...","gap_type":"misconception|missing_prerequisite|careless|other",'
            f'"knowledge_gap":"...","study_suggestion":"...","confidence":0.0,"relevant_source_indices":[1]}}'
        )
        few_shot = _DIAGNOSIS_FEW_SHOT_EN
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
    context = "\n---\n".join(f"[Nguồn {i+1}] {c}" for i, c in enumerate(context_chunks))
    existing = (
        "\n\nTRÁNH TRÙNG VỚI:\n" + "\n".join(f"- {q}" for q in existing_questions[:5])
        if existing_questions else ""
    )
    bloom_desc = {
        "remember":   ("Nhớ",       "Remember"),
        "understand": ("Hiểu",      "Understand"),
        "apply":      ("Vận dụng",  "Apply"),
        "analyze":    ("Phân tích", "Analyze"),
        "evaluate":   ("Đánh giá",  "Evaluate"),
        "create":     ("Sáng tạo",  "Create"),
    }
    bloom_vi, bloom_en = bloom_desc.get(bloom_level, ("Nhớ", "Remember"))
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
    if language == "vi":
        lang_note = (
            "LƯU Ý THIẾT KẾ:\n"
            "1. Tài liệu có thể bằng tiếng Anh. Đọc hiểu và viết câu hỏi + đáp án bằng tiếng Việt.\n"
            "2. Sử dụng Markdown (**đậm**, `mã`, $toán$, $$khối toán$$) một cách thông minh để câu hỏi chuyên nghiệp.\n"
            "3. TRÁNH BIAS: Các phương án nhiễu phải có vẻ đúng và liên quan đến chủ đề. Câu hỏi phải khách quan.\n"
            "4. TRÍ TUỆ: Câu hỏi phải đòi hỏi suy luận dựa trên tài liệu nguồn được cung cấp từ Knowledge Base."
        )
        user_msg = (
            f"TÀI LIỆU (Từ Vector DB/Graph):\n{context}{existing}\n\n{lang_note}\n\n"
            f"CHỦ ĐỀ: {node_name}\nCẤP ĐỘ BLOOM: {bloom_vi} ({bloom_level})\n\n"
            f"Tạo 1 câu hỏi trắc nghiệm chất lượng cao. Trả về JSON:\n{schema}"
        )
        few_shot = _QUIZ_FEW_SHOT_VI
    else:
        lang_note = (
            "DESIGN NOTES:\n"
            "1. Source materials may be in Vietnamese. Write questions and answers in English.\n"
            "2. Use Markdown (**bold**, `code`, $math$, $$math block$$) smartly for a professional feel.\n"
            "3. ANTI-BIAS: Ensure distractors are plausible and relevant. Question must be objective.\n"
            "4. INTELLIGENCE: The question must require reasoning based on the provided source material from the Knowledge Base."
        )
        user_msg = (
            f"MATERIAL (From Vector DB/Graph):\n{context}{existing}\n\n{lang_note}\n\n"
            f"TOPIC: {node_name}\nBLOOM LEVEL: {bloom_en}\n\n"
            f"Create 1 high-quality multiple choice question. Return JSON:\n{schema}"
        )
        few_shot = _QUIZ_FEW_SHOT_EN
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
    context = "\n---\n".join(f"[Nguồn {i+1}] {c}" for i, c in enumerate(context_chunks))
    avoid = (
        ("\nTRÁNH TRÙNG LẶP:\n" if language == "vi" else "\nDO NOT DUPLICATE:\n")
        + "\n".join(f"- {f}" for f in (existing_fronts or [])[:10])
        if existing_fronts else ""
    )
    schema = (
        '{"flashcards":[{"front_text":"[câu hỏi ngắn]","back_text":"[giải thích ngắn]"}]}'
    )
    if language == "vi":
        lang_note = "LƯU Ý: tài liệu có thể bằng tiếng Anh. Đọc hiểu và tạo flashcard bằng tiếng Việt."
        user_msg = (
            f"TÀI LIỆU:\n{context}\n\n{lang_note}\n\n"
            f"CHỦ ĐỀ: {node_name}\n"
            f"LỖI SAI GẦN ĐÂY:\n{wrong_answers_context}\n{avoid}\n"
            f"Tạo {count} flashcard MỚI. Trả về JSON:\n{schema}"
        )
        few_shot = _FLASHCARD_FEW_SHOT_VI
    else:
        lang_note = "NOTE: source materials may be in Vietnamese. Create flashcards in English."
        user_msg = (
            f"MATERIAL:\n{context}\n\n{lang_note}\n\n"
            f"TOPIC: {node_name}\n"
            f"RECENT ERRORS:\n{wrong_answers_context}\n{avoid}\n"
            f"Create {count} NEW flashcards. Return JSON:\n{schema}"
        )
        few_shot = []
    return [
        {"role": "system", "content": SYSTEM_PROMPT_FLASHCARD_GEN[language]},
        *few_shot,
        {"role": "user", "content": user_msg},
    ]


# ── Concept Check (Quick Action Panel mini-quiz) ───────────────────────────
SYSTEM_PROMPT_CONCEPT_CHECK = {
    "vi": (
        "Bạn là chuyên gia thiết kế câu hỏi 'Concept Check' siêu ngắn cho micro-lesson. "
        "Mỗi câu phải kiểm tra MỘT khái niệm cốt lõi vừa học, không hơn. "
        "Câu hỏi và phương án phải ngắn gọn, KHÔNG dài hơn một dòng. "
        "Tài liệu có thể bằng tiếng Anh — đọc hiểu và viết câu hỏi bằng tiếng Việt. "
        "Chỉ trả về JSON hợp lệ theo đúng schema, không thêm text khác."
    ),
    "en": (
        "You are an expert at designing ultra-short 'Concept Check' questions for a micro-lesson. "
        "Each question must test ONE core concept just learned, nothing more. "
        "Questions and options must be terse, no longer than one line. "
        "Source materials may be in Vietnamese — read them and write questions in English. "
        "Return ONLY valid JSON matching the schema, no extra text."
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
    topic = node_name or ("Bài học" if language == "vi" else "Lesson")
    if language == "vi":
        user_msg = (
            f"NỘI DUNG MICRO-LESSON:\n{text_chunk}\n\n"
            f"CHỦ ĐỀ: {topic}\n"
            f"Hãy tạo CHÍNH XÁC {count} câu hỏi 'Concept Check' kiểu trắc nghiệm "
            f"(SINGLE_CHOICE, 4 lựa chọn) bám sát nội dung trên. "
            f"Trả về JSON:\n{schema}"
        )
    else:
        user_msg = (
            f"MICRO-LESSON CONTENT:\n{text_chunk}\n\n"
            f"TOPIC: {topic}\n"
            f"Generate EXACTLY {count} SINGLE_CHOICE 'Concept Check' questions "
            f"(4 options each) grounded in the content above. "
            f"Return JSON:\n{schema}"
        )

    return [
        {"role": "system", "content": SYSTEM_PROMPT_CONCEPT_CHECK[language]},
        {"role": "user", "content": user_msg},
    ]