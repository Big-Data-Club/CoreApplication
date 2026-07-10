"""
ai-service/app/agents/core/context_formatter.py

GraphRAG Context Formatter.

Converts a GraphRAGContext object into structured text sections that
are injected into the LLM system prompt, enabling the model to:

  1. Understand the knowledge graph context (concept relationships)
  2. Follow the prerequisite learning path
  3. Prioritize weak-prerequisite concepts when personalizing explanations
  4. Cite evidence chunks with concept attribution

Output format (Markdown, injected into system prompt):
  ## Knowledge Graph Context
  ### Relevant Concepts
  ### Prerequisite Learning Path
  ### Student Mastery Signal   (omitted if no weak nodes)
  ### Evidence Chunks

Usage:
  from app.agents.core.context_formatter import graphrag_context_formatter
  graph_section = graphrag_context_formatter.format(ctx)
  # inject graph_section into system prompt
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.graphrag_service import GraphRAGContext

logger = logging.getLogger(__name__)

# Relationship labels in Vietnamese/English
RELATION_LABELS: dict[str, str] = {
    "PREREQUISITE":    "Tiên quyết (cần học trước)",
    "EXTENDS":         "Mở rộng / chuyên sâu hơn",
    "EQUIVALENT":      "Tương đương (cùng khái niệm)",
    "RELATED":         "Liên quan",
    "CONTRASTS_WITH":  "Đối lập / so sánh với",
}

MAX_CONCEPT_NODES = 8     # Cap concept nodes shown to LLM
MAX_PREREQ_LENGTH = 6     # Cap prereq chain length
MAX_CHUNK_TEXT_LEN = 300  # Trim chunk text to keep context compact


class GraphRAGContextFormatter:
    """
    Formats a GraphRAGContext into LLM-injectable Markdown sections.

    Design principles:
    - Compact: total output < 1500 chars under normal conditions
    - Informative: LLM gets enough graph signal to reason about relationships
    - Graceful: empty sections are suppressed, not shown as "(none)"
    """

    def format(self, ctx: "GraphRAGContext") -> str:
        """
        Format the full GraphRAGContext into a Markdown string.

        Returns empty string if no graph context is available (graceful
        fallback for non-graph retrieval paths).
        """
        if not ctx or not ctx.graph_expanded:
            return ""

        sections: list[str] = ["## Knowledge Graph Context"]

        # 1. Relevant Concepts
        concept_section = self._format_concepts(ctx)
        if concept_section:
            sections.append(concept_section)

        # 2. Prerequisite Learning Path
        prereq_section = self._format_prereq_chain(ctx)
        if prereq_section:
            sections.append(prereq_section)

        # 3. Student Mastery Signal (only when there are weak nodes)
        mastery_section = self._format_mastery_signal(ctx)
        if mastery_section:
            sections.append(mastery_section)

        if len(sections) == 1:
            # Only header, no content - skip entirely
            return ""

        return "\n\n".join(sections)

    def format_for_tool_result(self, ctx: "GraphRAGContext") -> dict:
        """
        Format GraphRAGContext as a structured dict for inclusion in
        tool results (search_course_materials, explain_concept).

        Keys:
          concept_relationships: list of {concept, related_to: [{name, rel_type}]}
          prereq_path:           list of concept names in order
          weak_prereqs:          list of weak concept names on the prereq path
          graph_expanded:        bool
        """
        if not ctx:
            return {"graph_expanded": False}

        # Concept relationships (seed nodes only, with their edges)
        concept_rels = []
        seed_ids = set(ctx.seed_node_ids)
        node_map = {cn.id: cn for cn in ctx.concept_nodes}

        for cn in ctx.concept_nodes:
            if not cn.is_seed:
                continue
            related = []
            for edge in ctx.edges:
                if edge.source == cn.id:
                    target_node = node_map.get(edge.target)
                    if target_node:
                        related.append({
                            "name": target_node.name_vi or target_node.name,
                            "relation": RELATION_LABELS.get(edge.relation_type, edge.relation_type),
                        })
                elif edge.target == cn.id:
                    source_node = node_map.get(edge.source)
                    if source_node:
                        related.append({
                            "name": source_node.name_vi or source_node.name,
                            "relation": f"← {RELATION_LABELS.get(edge.relation_type, edge.relation_type)}",
                        })
            concept_rels.append({
                "concept": cn.name_vi or cn.name,
                "course_id": cn.course_id,
                "related_to": related[:4],  # cap at 4 to keep compact
            })

        # Prereq path
        prereq_names = [
            cn.name_vi or cn.name
            for cn in ctx.prereq_chain[:MAX_PREREQ_LENGTH]
        ]

        # Weak prereqs (intersection of weak nodes and prereq path)
        weak_prereq_ids = set(ctx.weak_nodes.keys()) & set(ctx.prereq_node_ids)
        weak_prereq_names = [
            (node_map[nid].name_vi or node_map[nid].name)
            for nid in weak_prereq_ids
            if nid in node_map
        ]

        return {
            "graph_expanded": ctx.graph_expanded,
            "concept_relationships": concept_rels,
            "prereq_path": prereq_names,
            "weak_prereqs": weak_prereq_names,
            "seed_node_count": len(ctx.seed_node_ids),
            "expanded_node_count": len(ctx.expanded_node_ids),
        }

    # ── Private section builders ──────────────────────────────────────────────

    def _format_concepts(self, ctx: "GraphRAGContext") -> str:
        """Format the relevant concepts section."""
        if not ctx.concept_nodes:
            return ""

        node_map = {cn.id: cn for cn in ctx.concept_nodes}
        lines: list[str] = ["### Các khái niệm liên quan (Knowledge Graph)"]

        # Show seed nodes first, then top expanded neighbors
        seed_nodes = [cn for cn in ctx.concept_nodes if cn.is_seed]
        neighbor_nodes = [
            cn for cn in ctx.concept_nodes
            if not cn.is_seed and cn.hops <= 2
        ][:MAX_CONCEPT_NODES - len(seed_nodes)]

        all_display = seed_nodes + neighbor_nodes
        for cn in all_display:
            label = cn.name_vi or cn.name
            hop_hint = "" if cn.is_seed else f" (liên quan, {cn.hops} bước)"
            mastery_hint = ""
            if cn.mastery_score is not None and cn.mastery_score < 0.5:
                mastery_hint = " ⚠ [cần ôn lại]"

            # Find outgoing edges for this node
            edge_hints: list[str] = []
            for edge in ctx.edges:
                if edge.source == cn.id:
                    target = node_map.get(edge.target)
                    if target:
                        rel = RELATION_LABELS.get(edge.relation_type, edge.relation_type)
                        t_name = target.name_vi or target.name
                        edge_hints.append(f"{rel}: **{t_name}**")
                elif edge.target == cn.id and edge.relation_type == "PREREQUISITE":
                    source = node_map.get(edge.source)
                    if source:
                        s_name = source.name_vi or source.name
                        edge_hints.append(f"← phải biết trước: **{s_name}**")

            line = f"- **{label}**{hop_hint}{mastery_hint}"
            if edge_hints:
                line += "\n  - " + "\n  - ".join(edge_hints[:3])  # cap at 3
            lines.append(line)

        return "\n".join(lines)

    def _format_prereq_chain(self, ctx: "GraphRAGContext") -> str:
        """Format the prerequisite learning path."""
        if not ctx.prereq_chain or len(ctx.prereq_chain) < 2:
            return ""

        chain = ctx.prereq_chain[:MAX_PREREQ_LENGTH]
        names = [cn.name_vi or cn.name for cn in chain]
        path_str = " → ".join(f"**{n}**" for n in names)

        lines = [
            "### Lộ trình kiến thức tiên quyết",
            f"Để hiểu tốt chủ đề này, cần nắm vững theo thứ tự:",
            path_str,
        ]
        return "\n".join(lines)

    def _format_mastery_signal(self, ctx: "GraphRAGContext") -> str:
        """Format the student mastery signal section (only if weak nodes exist)."""
        if not ctx.weak_nodes:
            return ""

        node_map = {cn.id: cn for cn in ctx.concept_nodes}
        weak_in_prereq: list[str] = []
        weak_other: list[str] = []

        prereq_set = set(ctx.prereq_node_ids)
        for nid, score in ctx.weak_nodes.items():
            node = node_map.get(nid)
            name = (node.name_vi or node.name) if node else f"node_{nid}"
            if nid in prereq_set:
                weak_in_prereq.append(name)
            else:
                weak_other.append(name)

        if not weak_in_prereq and not weak_other:
            return ""

        lines = ["### Tín hiệu cá nhân hóa"]
        if weak_in_prereq:
            names_str = ", ".join(f"**{n}**" for n in weak_in_prereq)
            lines.append(
                f"⚠ Học viên đang yếu ở kiến thức tiên quyết: {names_str}. "
                f"Hãy ưu tiên giải thích những khái niệm này trước khi đi vào nội dung chính."
            )
        if weak_other:
            names_str = ", ".join(f"**{n}**" for n in weak_other[:3])
            lines.append(
                f"ℹ Kiến thức liên quan cần củng cố: {names_str}."
            )

        return "\n".join(lines)


# Module-level singleton
graphrag_context_formatter = GraphRAGContextFormatter()
