"""
ai-service/app/services/graphrag_service.py

GraphRAG Core Service - Graph-Augmented Retrieval Pipeline.

This service orchestrates the full GraphRAG retrieval flow:

  Phase 1 - Standard retrieval (vector + keyword, existing RRF merge)
  Phase 2 - Graph expansion via Neo4j (multi-seed BFS traversal)
  Phase 3 - Neighbor chunk fetch (chunks for expanded concept nodes)
  Phase 4 - Graph-guided re-ranking (prerequisite path boost)
  Phase 5 - Final merge and deduplication

The public API is:
  graphrag_service.retrieve(query, plan, user_id, course_id, user_mastery)
      -> GraphRAGContext

GraphRAGContext is then consumed by:
  - context_formatter.py  (formats concept map for LLM injection)
  - search_materials.py   (returns enriched chunks to the agent)
  - explain_concept.py    (uses prereq chain to scaffold explanations)

Feature flag: GRAPHRAG_ENABLED=false falls back to standard rag_service.search()
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ConceptNode:
    """A knowledge graph node enriched with mastery information."""
    id: int
    name: str
    name_vi: str | None
    course_id: int | None
    description: str | None
    is_seed: bool = False        # True if came from initial retrieval
    hops: int = 0                # 0 = seed, 1..N = graph-expanded
    mastery_score: float | None = None  # None = unknown


@dataclass
class GraphEdge:
    """A directed relationship between two concept nodes."""
    source: int
    target: int
    relation_type: str           # PREREQUISITE | EXTENDS | EQUIVALENT | RELATED | CONTRASTS_WITH
    strength: float | None = None
    cross_course: bool = False
    reason: str | None = None


@dataclass
class GraphRAGContext:
    """
    Full GraphRAG retrieval result.

    Consumed by context_formatter.py to build the LLM-ready context block.
    """
    # Query that triggered this retrieval
    query: str

    # Ranked evidence chunks (vector + keyword + graph-expanded, re-ranked)
    ranked_chunks: list  # list[RetrievedChunk]

    # Concept nodes involved (seeds + expanded neighbors)
    concept_nodes: list[ConceptNode] = field(default_factory=list)

    # Edges within the subgraph
    edges: list[GraphEdge] = field(default_factory=list)

    # Ordered prerequisite chain for primary seed node (earliest → target)
    prereq_chain: list[ConceptNode] = field(default_factory=list)

    # Node IDs on the prereq path (used by graph_boost_rerank)
    prereq_node_ids: list[int] = field(default_factory=list)

    # Mastery signals for weak nodes (node_id -> mastery_score)
    weak_nodes: dict[int, float] = field(default_factory=dict)

    # Whether graph expansion actually happened (False when disabled/failed)
    graph_expanded: bool = False

    # Debug/telemetry
    seed_node_ids: list[int] = field(default_factory=list)
    expanded_node_ids: list[int] = field(default_factory=list)
    total_candidates: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# GraphRAG Service
# ─────────────────────────────────────────────────────────────────────────────

class GraphRAGService:
    """
    Orchestrates the full Graph-Augmented Retrieval pipeline.

    All methods are async and safe to call concurrently.
    All graph operations fall back gracefully when Neo4j is unavailable.
    """

    async def retrieve(
        self,
        query: str,
        course_id: int | None = None,
        content_id: int | None = None,
        node_id: int | None = None,
        top_k: int | None = None,
        min_similarity: float = 0.25,
        expansion_enabled: bool = True,
        max_expansion_level: str = "global",
        user_id: int | None = None,
        weak_node_ids: list[int] | None = None,
        content_ids: list[int] | None = None,
    ) -> GraphRAGContext:
        """
        Execute the full GraphRAG retrieval pipeline.

        Args:
            query:               User query / concept to search for.
            course_id:           Optional course scope filter.
            content_id:          Optional content scope filter.
            node_id:             Optional node scope filter.
            top_k:               Final number of chunks to return.
            min_similarity:      Minimum similarity threshold.
            expansion_enabled:   Whether graph expansion is active.
            max_expansion_level: Scope cap for RAG hierarchical expansion.
            user_id:             Used for telemetry only.
            weak_node_ids:       Node IDs where user has mastery < threshold.
                                 Used for prerequisite boost re-ranking.
            content_ids:         Optional list of content_ids to restrict search.

        Returns:
            GraphRAGContext with ranked_chunks, concept_nodes, edges, prereq_chain.
        """
        from app.services.rag_service import rag_service

        top_k = top_k or settings.top_k_chunks
        ctx = GraphRAGContext(query=query)

        # ── Phase 1: Standard hierarchical retrieval ──────────────────────────
        try:
            raw_chunks, resolved_scope = await rag_service.search_hierarchical(
                query=query,
                course_id=course_id,
                content_id=content_id,
                top_k=top_k * 3,          # fetch wider for re-ranking
                min_similarity=min_similarity,
                expansion_enabled=expansion_enabled,
                max_expansion_level=max_expansion_level,
                content_ids=content_ids,
            )
        except Exception as exc:
            logger.error("GraphRAG Phase 1 (standard retrieval) failed: %s", exc)
            raw_chunks = []
            resolved_scope = "error"

        ctx.total_candidates = len(raw_chunks)

        if not settings.graphrag_enabled or not settings.neo4j_enabled:
            # Feature-flag off: return standard results as-is
            ctx.ranked_chunks = raw_chunks[:top_k]
            return ctx

        # ── Phase 2: Graph expansion (Neo4j) ─────────────────────────────────
        seed_node_ids = self._extract_node_ids(raw_chunks)
        ctx.seed_node_ids = seed_node_ids

        if not seed_node_ids:
            ctx.ranked_chunks = raw_chunks[:top_k]
            return ctx

        graph_data, prereq_chain = await asyncio.gather(
            self._expand_graph(seed_node_ids),
            self._get_prereq_chain(seed_node_ids[0]),  # primary seed
            return_exceptions=True,
        )

        # Handle exceptions from gather
        if isinstance(graph_data, Exception):
            logger.warning("Graph expansion failed: %s", graph_data)
            graph_data = {"seed_node_ids": seed_node_ids, "expanded_nodes": [], "edges": []}
        if isinstance(prereq_chain, Exception):
            logger.warning("Prereq chain failed: %s", prereq_chain)
            prereq_chain = []

        expanded_nodes_raw = graph_data.get("expanded_nodes", [])
        edges_raw = graph_data.get("edges", [])
        expanded_node_ids = [n["id"] for n in expanded_nodes_raw]
        ctx.expanded_node_ids = expanded_node_ids
        ctx.graph_expanded = bool(expanded_node_ids)

        # Build ConceptNode objects for seed nodes (fetch metadata)
        seed_node_meta = await self._fetch_node_metadata(seed_node_ids)
        concept_nodes: list[ConceptNode] = [
            ConceptNode(
                id=n["id"], name=n.get("name", ""), name_vi=n.get("name_vi"),
                course_id=n.get("course_id"), description=n.get("description"),
                is_seed=True, hops=0,
            )
            for n in seed_node_meta
        ]
        # Add expanded neighbor nodes
        for n in expanded_nodes_raw:
            concept_nodes.append(ConceptNode(
                id=n["id"], name=n.get("name", ""), name_vi=n.get("name_vi"),
                course_id=n.get("course_id"), description=n.get("description"),
                is_seed=False, hops=n.get("hops", 1),
            ))

        # Build GraphEdge objects
        edges = [
            GraphEdge(
                source=e["source"], target=e["target"],
                relation_type=e.get("relation_type", "RELATED"),
                strength=e.get("strength"), cross_course=bool(e.get("cross_course")),
                reason=e.get("reason"),
            )
            for e in edges_raw
        ]

        # Build prereq chain nodes
        prereq_node_ids: list[int] = []
        prereq_concept_nodes: list[ConceptNode] = []
        for n in (prereq_chain or []):
            nid = n.get("id") if isinstance(n, dict) else getattr(n, "id", None)
            if nid:
                prereq_node_ids.append(nid)
                prereq_concept_nodes.append(ConceptNode(
                    id=nid,
                    name=n.get("name", "") if isinstance(n, dict) else n.name,
                    name_vi=n.get("name_vi") if isinstance(n, dict) else getattr(n, "name_vi", None),
                    course_id=n.get("course_id") if isinstance(n, dict) else getattr(n, "course_id", None),
                    description=None,
                ))

        ctx.concept_nodes = concept_nodes
        ctx.edges = edges
        ctx.prereq_chain = prereq_concept_nodes
        ctx.prereq_node_ids = prereq_node_ids

        # ── Phase 3: Fetch neighbor chunks ────────────────────────────────────
        neighbor_chunks = []
        if expanded_node_ids:
            try:
                neighbor_chunks = await rag_service.search_by_node_ids(
                    node_ids=expanded_node_ids,
                    top_k=settings.graph_neighbor_top_k,
                    course_id=course_id,
                )
            except Exception as exc:
                logger.warning("GraphRAG Phase 3 (neighbor chunks) failed: %s", exc)

        # ── Phase 4: Merge + Graph-guided re-ranking ──────────────────────────
        # Combine primary chunks and neighbor chunks, deduplicate
        all_chunks = self._deduplicate(raw_chunks + neighbor_chunks)
        ctx.total_candidates = len(all_chunks)

        # Apply prerequisite boost if we have both weak nodes and prereq path
        if prereq_node_ids and weak_node_ids:
            # Only boost if user is weak in at least one prereq
            weak_set = set(weak_node_ids or [])
            has_weak_prereq = any(nid in weak_set for nid in prereq_node_ids)
            if has_weak_prereq:
                all_chunks = rag_service.graph_boost_rerank(
                    chunks=all_chunks,
                    prereq_path_node_ids=prereq_node_ids,
                    boost_factor=settings.graph_prereq_boost,
                )

        # Attach mastery scores to concept nodes
        if weak_node_ids:
            weak_set = set(weak_node_ids)
            ctx.weak_nodes = {nid: 0.3 for nid in weak_set}  # placeholder score
            for cn in ctx.concept_nodes:
                if cn.id in weak_set:
                    cn.mastery_score = 0.3

        # ── Phase 5: Final rerank + trim ─────────────────────────────────────
        if settings.use_reranker and all_chunks:
            try:
                from app.core.embeddings import rerank_chunks
                all_chunks = await rerank_chunks(
                    query=query,
                    chunks=all_chunks,
                    text_fn=lambda c: c.chunk_text,
                    top_k=top_k,
                )
            except Exception as exc:
                logger.warning("GraphRAG reranker failed (non-fatal): %s", exc)
                all_chunks = all_chunks[:top_k]
        else:
            all_chunks = all_chunks[:top_k]

        ctx.ranked_chunks = all_chunks
        logger.info(
            "GraphRAG retrieve: query='%s' seed_nodes=%d expanded=%d "
            "raw_chunks=%d neighbor_chunks=%d final=%d prereq_len=%d",
            query[:60], len(seed_node_ids), len(expanded_node_ids),
            len(raw_chunks), len(neighbor_chunks), len(ctx.ranked_chunks),
            len(prereq_node_ids),
        )

        return ctx

    # ── Internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _extract_node_ids(chunks: list) -> list[int]:
        """Extract unique non-None node_ids from retrieved chunks."""
        seen: set[int] = set()
        result: list[int] = []
        for chunk in chunks:
            nid = getattr(chunk, "node_id", None)
            if nid and nid not in seen:
                seen.add(nid)
                result.append(nid)
        return result

    async def _expand_graph(self, seed_node_ids: list[int]) -> dict:
        from app.services.neo4j_service import neo4j_service
        return await neo4j_service.get_concept_context(
            node_ids=seed_node_ids,
            depth=settings.graph_context_depth,
        )

    async def _get_prereq_chain(self, target_node_id: int) -> list[dict]:
        from app.services.neo4j_service import neo4j_service
        return await neo4j_service.get_prerequisite_chain(
            target_node_id=target_node_id,
            max_depth=4,
        )

    async def _fetch_node_metadata(self, node_ids: list[int]) -> list[dict]:
        """Fetch node name/description metadata for seed nodes."""
        if not node_ids:
            return []
        try:
            from app.services.neo4j_service import neo4j_service
            return await neo4j_service.get_nodes_by_ids(node_ids)
        except Exception as exc:
            logger.warning("_fetch_node_metadata failed: %s", exc)
            return []

    @staticmethod
    def _deduplicate(chunks: list) -> list:
        """Remove duplicate chunks by chunk_id, preserving first occurrence."""
        seen: set[int] = set()
        result = []
        for chunk in chunks:
            cid = getattr(chunk, "chunk_id", None)
            if cid is not None and cid in seen:
                continue
            if cid is not None:
                seen.add(cid)
            result.append(chunk)
        return result


# Module-level singleton
graphrag_service = GraphRAGService()
