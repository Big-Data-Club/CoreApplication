-- V004: Expand knowledge_node_relations.relation_type CHECK constraint
-- to match the five relationship types used in Neo4j and graph_linker.
--
-- Old: CHECK (relation_type IN ('prerequisite', 'related', 'extends'))
-- New: CHECK (relation_type IN ('prerequisite', 'related', 'extends', 'equivalent', 'contrasts_with'))

ALTER TABLE knowledge_node_relations
    DROP CONSTRAINT IF EXISTS knowledge_node_relations_relation_type_check;

ALTER TABLE knowledge_node_relations
    ADD CONSTRAINT knowledge_node_relations_relation_type_check
        CHECK (relation_type IN ('prerequisite', 'related', 'extends', 'equivalent', 'contrasts_with'));
