"""
ai-service/app/services/neo4j_service.py

Knowledge Graph backend using Neo4j.

Design:
  - Every KnowledgeNode in PostgreSQL gets a mirror node in Neo4j.
  - Relationships are stored ONLY in Neo4j - richer traversal, no N² PG joins.
  - Cross-course edges are first-class: tagged with cross_course=true.
  - Node identity = PostgreSQL id (BIGINT) - no extra mapping table.

Relationship types (directional where it matters):
  PREREQUISITE  source must be understood before target
  EXTENDS       target deepens / continues source
  EQUIVALENT    same concept in different courses / languages
  RELATED       semantically similar but no clear direction
  CONTRASTS_WITH  opposing / comparative concepts

Queries:
  - get_course_graph(course_id)  -> intra-course nodes + all their edges
  - get_global_graph()           -> all nodes, all edges
  - find_cross_course_neighbors(node_id, depth) -> used by AI agent
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from neo4j import AsyncGraphDatabase, AsyncDriver
from neo4j.exceptions import ServiceUnavailable

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Relationship constants ─────────────────────────────────────────────────────

RELATIONSHIP_TYPES = {
    "prerequisite":    "PREREQUISITE",
    "extends":         "EXTENDS",
    "equivalent":      "EQUIVALENT",
    "related":         "RELATED",
    "contrasts_with":  "CONTRASTS_WITH",
}

# Similarity thresholds
INTRA_COURSE_THRESHOLD  = 0.62   # Same course - more lenient
CROSS_COURSE_THRESHOLD  = 0.82   # Different courses - tighter to avoid noise, but lowered for better recall
EQUIVALENT_THRESHOLD    = 0.95   # Very high -> likely same concept


class Neo4jService:
    """
    Async Neo4j driver wrapper.
    Call `init()` once at startup; `close()` at shutdown.
    """

    _driver: AsyncDriver | None = None

    async def init(self) -> None:
        uri      = settings.neo4j_uri
        user     = settings.neo4j_user
        password = settings.neo4j_password
        self._driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
        # Verify connectivity
        try:
            await self._driver.verify_connectivity()
            logger.info("Neo4j connected: %s", uri)
        except ServiceUnavailable as exc:
            logger.error("Neo4j unavailable: %s", exc)

        await self._ensure_constraints()

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
            self._driver = None

    def _get_driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("Neo4j driver not initialised - call init()")
        return self._driver

    # ── Schema ─────────────────────────────────────────────────────────────────

    async def _ensure_constraints(self) -> None:
        """Idempotent: create uniqueness constraint + indexes."""
        async with self._get_driver().session() as s:
            # Unique constraint on (id) - maps 1:1 to PostgreSQL
            await s.run(
                "CREATE CONSTRAINT kn_id IF NOT EXISTS "
                "FOR (n:KnowledgeNode) REQUIRE n.id IS UNIQUE"
            )
            # Index course_id for fast per-course queries
            await s.run(
                "CREATE INDEX kn_course IF NOT EXISTS "
                "FOR (n:KnowledgeNode) ON (n.course_id)"
            )
        logger.debug("Neo4j constraints/indexes ensured")

    # ── Node CRUD ──────────────────────────────────────────────────────────────

    async def upsert_node(self, node: dict[str, Any]) -> None:
        """
        Create or update a KnowledgeNode.
        node must contain: id, course_id, name, name_vi, name_en,
                           description, auto_generated, source_content_id
        """
        async with self._get_driver().session() as s:
            await s.run(
                """
                MERGE (n:KnowledgeNode {id: $id})
                SET   n.course_id         = $course_id,
                      n.name              = $name,
                      n.name_vi           = $name_vi,
                      n.name_en           = $name_en,
                      n.description       = $description,
                      n.auto_generated    = $auto_generated,
                      n.source_content_id = $source_content_id,
                      n.updated_at        = datetime()
                """,
                **node,
            )

    async def upsert_nodes_batch(self, nodes: list[dict[str, Any]]) -> None:
        """Batch upsert - single round-trip via UNWIND."""
        async with self._get_driver().session() as s:
            await s.run(
                """
                UNWIND $nodes AS node
                MERGE (n:KnowledgeNode {id: node.id})
                SET   n.course_id         = node.course_id,
                      n.name              = node.name,
                      n.name_vi           = node.name_vi,
                      n.name_en           = node.name_en,
                      n.description       = node.description,
                      n.auto_generated    = node.auto_generated,
                      n.source_content_id = node.source_content_id,
                      n.updated_at        = datetime()
                """,
                nodes=nodes,
            )

    async def delete_node(self, node_id: int) -> None:
        async with self._get_driver().session() as s:
            await s.run(
                "MATCH (n:KnowledgeNode {id: $id}) DETACH DELETE n",
                id=node_id,
            )

    # ── Relationship CRUD ──────────────────────────────────────────────────────

    async def upsert_relationship(
        self,
        source_id: int,
        target_id: int,
        rel_type: str,            # one of RELATIONSHIP_TYPES values
        strength: float,
        auto_generated: bool = True,
        cross_course: bool = False,
        reason: str = "",
    ) -> None:
        """
        Create or update a typed, directional relationship.
        Uses MERGE so re-running is safe.
        """
        cypher = f"""
            MATCH (a:KnowledgeNode {{id: $src}}),
                  (b:KnowledgeNode {{id: $tgt}})
            MERGE (a)-[r:{rel_type}]->(b)
            SET   r.strength       = CASE WHEN r.strength IS NULL
                                         THEN $strength
                                         ELSE GREATEST(r.strength, $strength) END,
                  r.auto_generated = $auto_generated,
                  r.cross_course   = $cross_course,
                  r.reason         = $reason,
                  r.updated_at     = datetime()
        """
        async with self._get_driver().session() as s:
            await s.run(
                cypher,
                src=source_id,
                tgt=target_id,
                strength=round(strength, 3),
                auto_generated=auto_generated,
                cross_course=cross_course,
                reason=reason,
            )

    async def upsert_relationships_batch(
        self, edges: list[dict[str, Any]]
    ) -> None:
        """
        Batch upsert relationships.
        Each edge dict: {source_id, target_id, rel_type, strength,
                         auto_generated, cross_course, reason}
        """
        if not edges:
            return

        # Group by rel_type so we can use typed MERGE in Cypher
        from collections import defaultdict
        by_type: dict[str, list] = defaultdict(list)
        for e in edges:
            by_type[e["rel_type"]].append(e)

        async with self._get_driver().session() as s:
            for rel_type, batch in by_type.items():
                cypher = f"""
                    UNWIND $edges AS e
                    MATCH (a:KnowledgeNode {{id: e.source_id}}),
                          (b:KnowledgeNode {{id: e.target_id}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET   r.strength       = CASE 
                                                 WHEN r.strength IS NULL THEN e.strength
                                                 WHEN r.strength > e.strength THEN r.strength
                                                 ELSE e.strength 
                                             END,
                          r.auto_generated = e.auto_generated,
                          r.cross_course   = e.cross_course,
                          r.reason         = e.reason,
                          r.updated_at     = datetime()
                """
                await s.run(cypher, edges=batch)

    # ── Graph Queries ──────────────────────────────────────────────────────────

    async def get_course_graph(self, course_id: int) -> dict[str, Any]:
        """
        Returns all nodes for a course + ALL their edges (intra + cross-course).
        This lets the frontend show which course-B nodes are connected to course-A.
        """
        async with self._get_driver().session() as s:
            # Nodes in this course
            node_result = await s.run(
                """
                MATCH (n:KnowledgeNode {course_id: $course_id})
                RETURN n.id              AS id,
                       n.name            AS name,
                       n.name_vi         AS name_vi,
                       n.name_en         AS name_en,
                       n.description     AS description,
                       n.auto_generated  AS auto_generated,
                       n.source_content_id AS source_content_id,
                       n.course_id       AS course_id
                ORDER BY id
                """,
                course_id=course_id,
            )
            nodes = [dict(r) async for r in node_result]

            if not nodes:
                return {"nodes": [], "edges": []}

            node_ids = [n["id"] for n in nodes]

            # All edges where at least one endpoint is in this course
            edge_result = await s.run(
                """
                MATCH (a:KnowledgeNode)-[r]->(b:KnowledgeNode)
                WHERE (a.id IN $ids OR b.id IN $ids)
                RETURN a.id              AS source,
                       b.id              AS target,
                       type(r)           AS relation_type,
                       r.strength        AS strength,
                       r.auto_generated  AS auto_generated,
                       r.cross_course    AS cross_course,
                       r.reason          AS reason
                """,
                ids=node_ids,
            )
            edges = [dict(r) async for r in edge_result]

        return {"nodes": nodes, "edges": edges}

    async def get_global_graph(
        self,
        limit_nodes: int = 2000,
        min_strength: float = 0.5,
    ) -> dict[str, Any]:
        """
        Returns entire knowledge graph across all courses.
        Paginated by limit_nodes; edges filtered by min_strength.
        Used for admin dashboard / AI agent full-context mode.
        """
        async with self._get_driver().session() as s:
            node_result = await s.run(
                """
                MATCH (n:KnowledgeNode)
                RETURN n.id             AS id,
                       n.name           AS name,
                       n.name_vi        AS name_vi,
                       n.name_en        AS name_en,
                       n.description    AS description,
                       n.auto_generated AS auto_generated,
                       n.course_id      AS course_id,
                       n.source_content_id AS source_content_id
                ORDER BY n.course_id, n.id
                LIMIT $limit
                """,
                limit=limit_nodes,
            )
            nodes = [dict(r) async for r in node_result]

            edge_result = await s.run(
                """
                MATCH (a:KnowledgeNode)-[r]->(b:KnowledgeNode)
                WHERE r.strength >= $min_strength
                RETURN a.id             AS source,
                       b.id             AS target,
                       type(r)          AS relation_type,
                       r.strength       AS strength,
                       r.auto_generated AS auto_generated,
                       r.cross_course   AS cross_course,
                       r.reason         AS reason
                ORDER BY r.strength DESC
                LIMIT 10000
                """,
                min_strength=min_strength,
            )
            edges = [dict(r) async for r in edge_result]

        return {"nodes": nodes, "edges": edges}

    async def get_node_neighbors(
        self,
        node_id: int,
        max_depth: int = 2,
        max_nodes: int = 50,
    ) -> dict[str, Any]:
        """
        BFS from node_id up to max_depth hops.
        Traverses ALL relationship types, including cross-course.
        Used by the AI learning agent to discover related knowledge.
        """
        async with self._get_driver().session() as s:
            result = await s.run(
                """
                MATCH path = (start:KnowledgeNode {id: $node_id})
                             -[*1..$depth]-(neighbor:KnowledgeNode)
                WITH DISTINCT neighbor,
                     MIN(length(path)) AS hops
                ORDER BY hops, neighbor.id
                LIMIT $limit
                RETURN neighbor.id              AS id,
                       neighbor.name            AS name,
                       neighbor.name_vi         AS name_vi,
                       neighbor.course_id       AS course_id,
                       neighbor.description     AS description,
                       hops
                """,
                node_id=node_id,
                depth=max_depth,
                limit=max_nodes,
            )
            neighbors = [dict(r) async for r in result]

            # Also get the edges within the subgraph
            neighbor_ids = [n["id"] for n in neighbors] + [node_id]
            edge_result = await s.run(
                """
                MATCH (a:KnowledgeNode)-[r]->(b:KnowledgeNode)
                WHERE a.id IN $ids AND b.id IN $ids
                RETURN a.id AS source, b.id AS target,
                       type(r) AS relation_type,
                       r.strength AS strength,
                       r.cross_course AS cross_course
                """,
                ids=neighbor_ids,
            )
            edges = [dict(r) async for r in edge_result]

        return {"center_id": node_id, "neighbors": neighbors, "edges": edges}

    async def find_prerequisite_path(
        self, from_node_id: int, to_node_id: int
    ) -> list[dict]:
        """
        Find shortest prerequisite path between two nodes.
        Useful for AI agent to explain learning order.
        """
        async with self._get_driver().session() as s:
            result = await s.run(
                """
                MATCH path = shortestPath(
                    (a:KnowledgeNode {id: $from_id})
                    -[:PREREQUISITE*]->(b:KnowledgeNode {id: $to_id})
                )
                UNWIND nodes(path) AS n
                RETURN n.id AS id, n.name AS name,
                       n.name_vi AS name_vi, n.course_id AS course_id
                """,
                from_id=from_node_id,
                to_id=to_node_id,
            )
            return [dict(r) async for r in result]

    async def get_nodes_for_course_with_embeddings(
        self, course_id: int
    ) -> list[dict]:
        """Used internally by deduplication - returns id + name only."""
        async with self._get_driver().session() as s:
            result = await s.run(
                """
                MATCH (n:KnowledgeNode {course_id: $course_id})
                RETURN n.id AS id, n.name AS name, n.name_vi AS name_vi
                """,
                course_id=course_id,
            )
            return [dict(r) async for r in result]

    async def get_all_nodes_except_course(
        self, course_id: int, limit: int = 500
    ) -> list[dict]:
        """
        For cross-course linking: fetch nodes from OTHER courses.
        Returns id + name only (embeddings live in Qdrant/memory).
        """
        async with self._get_driver().session() as s:
            result = await s.run(
                """
                MATCH (n:KnowledgeNode)
                WHERE n.course_id <> $course_id
                RETURN n.id AS id, n.name AS name,
                       n.name_vi AS name_vi, n.course_id AS course_id
                ORDER BY n.id DESC
                LIMIT $limit
                """,
                course_id=course_id,
                limit=limit,
            )
            return [dict(r) async for r in result]

    # ── GraphRAG: Concept Context Expansion ────────────────────────────────────

    async def get_concept_context(
        self,
        node_ids: list[int],
        depth: int = 2,
        max_nodes: int = 40,
    ) -> dict[str, Any]:
        """
        Expand a set of seed node_ids into a subgraph of related concepts.

        This is the primary GraphRAG expansion step: given the node_ids
        attached to initially retrieved chunks, we traverse the knowledge graph
        up to `depth` hops and collect:
          - All expanded nodes (id, name, name_vi, course_id, description)
          - All relationship edges within the subgraph
            (source, target, relation_type, strength, cross_course)

        Returns:
            {
                "seed_node_ids": [...],
                "expanded_nodes": [{id, name, name_vi, course_id, description, hops}],
                "edges": [{source, target, relation_type, strength, cross_course}],
            }
        Falls back to empty result if Neo4j is disabled or query fails.
        """
        from app.core.config import get_settings
        _settings = get_settings()
        if not _settings.neo4j_enabled or not node_ids:
            return {"seed_node_ids": node_ids, "expanded_nodes": [], "edges": []}

        try:
            async with self._get_driver().session() as s:
                # Multi-seed BFS expansion: start from any seed node,
                # traverse up to `depth` hops in any direction.
                result = await s.run(
                    """
                    UNWIND $seed_ids AS seed_id
                    MATCH path = (start:KnowledgeNode {id: seed_id})
                                 -[*1..$depth]-(neighbor:KnowledgeNode)
                    WHERE NOT neighbor.id IN $seed_ids
                    WITH DISTINCT neighbor,
                         MIN(length(path)) AS hops
                    ORDER BY hops, neighbor.id
                    LIMIT $limit
                    RETURN neighbor.id          AS id,
                           neighbor.name        AS name,
                           neighbor.name_vi     AS name_vi,
                           neighbor.course_id   AS course_id,
                           neighbor.description AS description,
                           hops
                    """,
                    seed_ids=node_ids,
                    depth=depth,
                    limit=max_nodes,
                )
                expanded = [dict(r) async for r in result]

                # Fetch edges within the full subgraph (seeds + expanded)
                all_ids = node_ids + [n["id"] for n in expanded]
                edge_result = await s.run(
                    """
                    MATCH (a:KnowledgeNode)-[r]->(b:KnowledgeNode)
                    WHERE a.id IN $ids AND b.id IN $ids
                    RETURN a.id           AS source,
                           b.id           AS target,
                           type(r)        AS relation_type,
                           r.strength     AS strength,
                           r.cross_course AS cross_course,
                           r.reason       AS reason
                    """,
                    ids=all_ids,
                )
                edges = [dict(r) async for r in edge_result]

            return {
                "seed_node_ids":  node_ids,
                "expanded_nodes": expanded,
                "edges":          edges,
            }

        except Exception as exc:
            logger.warning("get_concept_context failed (non-fatal): %s", exc)
            return {"seed_node_ids": node_ids, "expanded_nodes": [], "edges": []}

    # ── GraphRAG: Prerequisite Chain ──────────────────────────────────────────

    async def get_prerequisite_chain(
        self,
        target_node_id: int,
        max_depth: int = 4,
    ) -> list[dict]:
        """
        Return the ordered prerequisite chain leading TO `target_node_id`.

        Traverses PREREQUISITE edges in reverse (prerequisites → target) and
        returns nodes ordered from earliest prerequisite to the target itself.
        Used by the GraphRAG formatter to produce a "learning path" hint for
        the LLM.

        Returns [] when Neo4j is disabled, the node has no prerequisites, or
        the query fails.
        """
        from app.core.config import get_settings
        _settings = get_settings()
        if not _settings.neo4j_enabled:
            return []

        try:
            async with self._get_driver().session() as s:
                result = await s.run(
                    """
                    MATCH path = (prereq:KnowledgeNode)
                                 -[:PREREQUISITE*1..$depth]->(target:KnowledgeNode {id: $target_id})
                    WITH nodes(path) AS path_nodes, length(path) AS path_len
                    ORDER BY path_len DESC
                    LIMIT 1
                    UNWIND path_nodes AS n
                    RETURN n.id        AS id,
                           n.name      AS name,
                           n.name_vi   AS name_vi,
                           n.course_id AS course_id
                    """,
                    target_id=target_node_id,
                    depth=max_depth,
                )
                return [dict(r) async for r in result]

        except Exception as exc:
            logger.warning(
                "get_prerequisite_chain for node=%d failed (non-fatal): %s",
                target_node_id, exc,
            )
            return []

    # ── GraphRAG: Nodes Lookup by IDs ─────────────────────────────────────────

    async def get_nodes_by_ids(self, node_ids: list[int]) -> list[dict]:
        """
        Fetch node metadata for a list of known IDs in a single round-trip.
        Used by graphrag_service to enrich chunk results with node names.
        """
        if not node_ids:
            return []
        from app.core.config import get_settings
        if not get_settings().neo4j_enabled:
            return []
        try:
            async with self._get_driver().session() as s:
                result = await s.run(
                    """
                    UNWIND $ids AS nid
                    MATCH (n:KnowledgeNode {id: nid})
                    RETURN n.id          AS id,
                           n.name        AS name,
                           n.name_vi     AS name_vi,
                           n.course_id   AS course_id,
                           n.description AS description
                    """,
                    ids=node_ids,
                )
                return [dict(r) async for r in result]
        except Exception as exc:
            logger.warning("get_nodes_by_ids failed (non-fatal): %s", exc)
            return []

    # ── Health ─────────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, Any]:
        try:
            async with self._get_driver().session() as s:
                r = await s.run(
                    """
                    MATCH (n:KnowledgeNode)
                    RETURN count(n) AS total_nodes,
                           count(DISTINCT n.course_id) AS total_courses
                    """
                )
                row = await r.single()
                rel_r = await s.run(
                    "MATCH ()-[r]->() RETURN count(r) AS total_edges"
                )
                rel_row = await rel_r.single()
            return {
                "status":        "ok",
                "total_nodes":   row["total_nodes"],
                "total_courses": row["total_courses"],
                "total_edges":   rel_row["total_edges"],
            }
        except Exception as exc:
            return {"status": "error", "detail": str(exc)}


neo4j_service = Neo4jService()