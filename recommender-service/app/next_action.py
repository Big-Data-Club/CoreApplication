"""One deterministic policy for daily, chat and next-best-lesson surfaces."""


def next_actions(profile: dict, minutes: int = 20, prefer_format: str = "mixed") -> list[dict]:
    states = {s["skill_id"]: s for s in profile.get("skill_states", [])}
    grouped: dict[int, list[dict]] = {}
    for content in profile.get("available_content", []):
        practice = content.get("content_type", "").upper() in {"QUIZ", "EXERCISE", "FLASHCARD", "MICRO_QUIZ"}
        if (prefer_format == "practice" and not practice) or (prefer_format == "theory" and practice):
            continue
        if content.get("prerequisites_met", True):
            grouped.setdefault(content["content_id"], []).append(content)
    ranked = []
    next_added = False
    resumes = [items[0] for items in grouped.values() if items[0].get("started") and not items[0].get("completed")]
    def activity(item):
        value = item.get("last_activity_at") or ""
        # Go's sql.NullTime JSON representation is kept backwards-compatible.
        return value.get("Time", "") if isinstance(value, dict) else value
    resume_id = max(resumes, key=activity)["content_id"] if resumes else None
    for content_id, mappings in grouped.items():
        item = mappings[0]
        weak = next((s for c in mappings if (s := states.get(c.get("skill_id")))
                     and s.get("attempt_count", 0) >= 2 and s.get("mastery_score", 1) < 0.6), None)
        if weak:
            score, action = 0.95, "review"
            reason = f"Ôn {weak.get('skill_name') or 'kỹ năng này'}: kết quả gần đây cho thấy cần củng cố ({weak['mastery_score']:.0%} thành thạo)."
        elif content_id == resume_id:
            score, action = 0.90, "continue_lesson"
            reason = "Tiếp tục nội dung bạn đã học nhưng chưa hoàn thành."
        elif not item.get("completed") and not next_added:
            score, action = 0.70, "learn_new"
            reason = "Nội dung chưa hoàn thành kế tiếp theo thứ tự giáo trình."
            next_added = True
        else:
            continue
        # Author-declared prerequisites were checked by LMS; no fabricated claims.
        ranked.append({
            "content_id": content_id, "title": item["content_title"],
            "skill_id": weak["skill_id"] if weak else item.get("skill_id", 0),
            "skill_name": weak.get("skill_name", "") if weak else item.get("skill_name", ""),
            "difficulty": item.get("difficulty", 0.5), "score": score,
            "action": action, "reason": reason, "estimated_minutes": min(minutes, 10),
        })
    ranked.sort(key=lambda item: -item["score"])
    selected, remaining = [], minutes
    for item in ranked:
        if remaining < 5 or len(selected) == 3:
            break
        item["estimated_minutes"] = min(item["estimated_minutes"], remaining)
        selected.append(item)
        remaining -= item["estimated_minutes"]
    return selected
