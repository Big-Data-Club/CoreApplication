# ADR-003: Neo4j for Cross-Course Knowledge Graph

| Field    | Value                          |
|----------|--------------------------------|
| Status   | Accepted                       |
| Date     | 2025-01-01                     |
| Authors  | BDC Team                       |

## Context

The AI service builds a knowledge graph where nodes are learning concepts
(`knowledge_nodes`) and edges represent relationships (prerequisite, extends,
related, equivalent). This graph is used for:

1. Adaptive learning path generation
2. Cross-course prerequisite discovery
3. AI agent context building (BFS traversal from a query node)

The initial implementation stored edges in a `knowledge_node_relations` table
in PostgreSQL. This works for intra-course graphs but has two limitations:

1. **Cross-course traversal is expensive:** Finding cross-course relationships
   requires a self-join on `knowledge_node_relations` with a `WHERE course_id != X`
   filter, which becomes a full table scan as the graph grows.

2. **Variable-depth path queries are not expressive:** Finding the shortest
   prerequisite path between two nodes requires recursive CTEs in SQL. These
   are correct but verbose and difficult to optimise beyond a depth of 3–4.

## Decision

Neo4j is added as the knowledge graph backend alongside PostgreSQL.
Nodes are mirrored from PostgreSQL to Neo4j at index time.
All graph traversal queries (course graph, global graph, neighbor BFS,
prerequisite paths) run against Neo4j when `NEO4J_ENABLED=true`.

PostgreSQL `knowledge_node_relations` is retained as a fallback and for
relational consistency (foreign keys to `knowledge_nodes`).

## Rationale

### Alternative A: Keep PostgreSQL with recursive CTEs
- Pros: No additional infrastructure
- Cons: Cypher `MATCH path = ... -[*1..4]->()` is far more readable than
  recursive CTE; PostgreSQL recursive queries are harder to optimise;
  cannot do variable-depth traversal efficiently beyond depth 3
- Reason rejected: Acceptable now but does not scale for the planned
  AI learning agent feature (requires depth 5+ traversals)

### Alternative B: In-memory graph (NetworkX)
- Pros: No additional service; very fast for small graphs
- Cons: Graph must be rebuilt on every restart; not shared between
  ai-service and ai-worker instances; not durable
- Reason rejected: Not suitable for production; hard to keep consistent

### Chosen: Neo4j (Community Edition)
- Native graph database: variable-depth traversal via Cypher is O(hops),
  not O(edges)
- MERGE semantics allow idempotent upserts - safe to re-run indexing
- Node identity uses PostgreSQL `id` (BIGINT) - no additional mapping table
- `neo4j=5.x` Python async client available
- Community Edition is sufficient for current scale

## Implementation

`NEO4J_ENABLED=true` controls whether Neo4j is used. When disabled, all
graph endpoints fall back to PostgreSQL queries.

Schema:
```
(:KnowledgeNode {id, course_id, name, name_vi, name_en, description,
                  auto_generated, source_content_id})

(:KnowledgeNode)-[:PREREQUISITE   {strength, auto_generated, cross_course}]->(:KnowledgeNode)
(:KnowledgeNode)-[:EXTENDS         {strength, auto_generated, cross_course}]->(:KnowledgeNode)
(:KnowledgeNode)-[:EQUIVALENT      {strength, auto_generated, cross_course}]->(:KnowledgeNode)
(:KnowledgeNode)-[:RELATED         {strength, auto_generated, cross_course}]->(:KnowledgeNode)
(:KnowledgeNode)-[:CONTRASTS_WITH  {strength, auto_generated, cross_course}]->(:KnowledgeNode)
```

Cross-course links are discovered by `graph_linker.py`:
1. Compute cosine similarity between new nodes and all nodes in other courses
   (using Qdrant batch search).
2. For pairs above threshold (0.82), call LLM to classify the relationship type.
3. Write confirmed relationships to Neo4j with `cross_course=true`.

## Consequences

### Positive
- Variable-depth BFS for AI agent context: `MATCH path = (n)-[*1..4]-(m)`
- Cross-course prerequisite paths expressible in one Cypher query
- Graph visualisation endpoint (`GET /knowledge-graph/{course_id}`) can
  include cross-course edges for a complete picture

### Negative
- Additional service to operate (Neo4j container, ~1.5 GB RAM)
- Nodes must be kept in sync between PostgreSQL and Neo4j at index time
- Neo4j downtime causes graph endpoints to return 501 (fallback to PG available)

### Risks
- Risk: Neo4j and PostgreSQL drift if a node is deleted in PG but not Neo4j.
  Mitigation: `DELETE /knowledge-graph/node/{id}` endpoint deletes from both.
  The `migrate_neo4j.py` script can re-sync from scratch if needed.

## References
- `ai-service/app/services/neo4j_service.py` - driver wrapper and queries
- `ai-service/app/services/graph_linker.py` - cross-course link discovery
- `ai-service/scripts/migrate_neo4j.py` - migration from PG to Neo4j
- `docker-compose.yml` - Neo4j service (port 7687)
