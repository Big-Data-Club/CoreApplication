"""Insert get_weak_nodes method into ltm.py"""
path = r'd:\CodeSpace\BDCApp\ai-service\app\agents\memory\ltm.py'
content = open(path, 'r', encoding='utf-8').read()

new_method = '''
    # -- GraphRAG: Weak Nodes for Re-ranking ----------------------------------

    async def get_weak_nodes(
        self,
        user_id: int,
        course_id=None,
        threshold: float = 0.5,
        limit: int = 20,
    ) -> list:
        """Return node_ids where the user mastery score is below threshold.

        Used by graphrag_service to drive prerequisite-aware retrieval re-ranking.

        Priority:
          1. mastery_scores table (primary)
          2. mastery_service.get_user_struggles() (spaced repetition fallback)
          3. Empty list (no mastery data available)
        """
        weak_node_ids: list = []

        # Attempt 1: mastery_scores table
        try:
            async with get_ai_conn() as conn:
                extra_cond = ""
                params: list = [user_id, threshold, limit]
                if course_id is not None:
                    extra_cond = " AND course_id = $4"
                    params.append(course_id)
                rows = await conn.fetch(
                    f"SELECT node_id FROM mastery_scores "
                    f"WHERE user_id = $1 AND mastery_level < $2 AND node_id IS NOT NULL{extra_cond} "
                    f"ORDER BY mastery_level ASC, last_reviewed DESC LIMIT $3",
                    *params,
                )
                if rows:
                    weak_node_ids = [r["node_id"] for r in rows]
                    logger.debug(
                        "get_weak_nodes: user=%d course=%s found %d weak nodes (mastery_scores)",
                        user_id, course_id, len(weak_node_ids),
                    )
                    return weak_node_ids
        except Exception:
            pass  # table may not exist

        # Attempt 2: mastery_service struggles
        try:
            from app.services.mastery_service import mastery_service
            struggles = await mastery_service.get_user_struggles(user_id=user_id, course_id=course_id)
            weak_node_ids = [
                s["node_id"] for s in (struggles or [])
                if s.get("mastery_level", 1.0) < threshold and s.get("node_id")
            ][:limit]
            if weak_node_ids:
                logger.debug(
                    "get_weak_nodes: user=%d course=%s found %d weak nodes (mastery_service)",
                    user_id, course_id, len(weak_node_ids),
                )
        except Exception as exc:
            logger.debug("get_weak_nodes fallback failed (non-fatal): %s", exc)

        return weak_node_ids

'''

marker = '# Singleton\nltm = LTMemory()\n'
if marker in content:
    content = content.replace(marker, new_method + '# Singleton\nltm = LTMemory()\n', 1)
    open(path, 'w', encoding='utf-8').write(content)
    print("SUCCESS")
    verify = open(path, encoding='utf-8').read()
    print("get_weak_nodes present:", 'get_weak_nodes' in verify)
else:
    print("MARKER NOT FOUND")
