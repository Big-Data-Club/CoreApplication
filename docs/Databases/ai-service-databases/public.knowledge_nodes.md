# public.knowledge_nodes

## Columns

| Name | Type | Default | Nullable | Children | Parents | Comment |
| ---- | ---- | ------- | -------- | -------- | ------- | ------- |
| id | bigint | nextval('knowledge_nodes_id_seq'::regclass) | false | [public.knowledge_nodes](public.knowledge_nodes.md) [public.knowledge_node_relations](public.knowledge_node_relations.md) [public.document_chunks](public.document_chunks.md) [public.ai_diagnoses](public.ai_diagnoses.md) [public.student_knowledge_progress](public.student_knowledge_progress.md) [public.spaced_repetitions](public.spaced_repetitions.md) [public.ai_quiz_generations](public.ai_quiz_generations.md) [public.flashcards](public.flashcards.md) |  |  |
| course_id | bigint |  | false |  |  |  |
| parent_id | bigint |  | true |  | [public.knowledge_nodes](public.knowledge_nodes.md) |  |
| name | varchar(255) |  | false |  |  |  |
| name_vi | varchar(255) |  | true |  |  |  |
| name_en | varchar(255) |  | true |  |  |  |
| description | text |  | true |  |  |  |
| level | integer | 0 | true |  |  |  |
| order_index | integer | 0 | true |  |  |  |
| source_content_id | bigint |  | true |  |  |  |
| source_content_title | text | ''::text | true |  |  |  |
| auto_generated | boolean | false | true |  |  |  |
| created_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |
| updated_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |

## Constraints

| Name | Type | Definition |
| ---- | ---- | ---------- |
| knowledge_nodes_course_id_not_null | n | NOT NULL course_id |
| knowledge_nodes_id_not_null | n | NOT NULL id |
| knowledge_nodes_name_not_null | n | NOT NULL name |
| knowledge_nodes_parent_id_fkey | FOREIGN KEY | FOREIGN KEY (parent_id) REFERENCES knowledge_nodes(id) ON DELETE SET NULL |
| knowledge_nodes_pkey | PRIMARY KEY | PRIMARY KEY (id) |

## Indexes

| Name | Definition |
| ---- | ---------- |
| knowledge_nodes_pkey | CREATE UNIQUE INDEX knowledge_nodes_pkey ON public.knowledge_nodes USING btree (id) |
| idx_kn_course | CREATE INDEX idx_kn_course ON public.knowledge_nodes USING btree (course_id) |
| idx_kn_parent | CREATE INDEX idx_kn_parent ON public.knowledge_nodes USING btree (parent_id) |
| idx_kn_level | CREATE INDEX idx_kn_level ON public.knowledge_nodes USING btree (course_id, level) |
| idx_kn_source | CREATE INDEX idx_kn_source ON public.knowledge_nodes USING btree (source_content_id) WHERE (source_content_id IS NOT NULL) |
| idx_kn_source_content | CREATE INDEX idx_kn_source_content ON public.knowledge_nodes USING btree (source_content_id, source_content_title) WHERE (source_content_id IS NOT NULL) |

## Triggers

| Name | Definition |
| ---- | ---------- |
| tr_kn_updated | CREATE TRIGGER tr_kn_updated BEFORE UPDATE ON public.knowledge_nodes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column() |

## Relations

```mermaid
erDiagram

"public.knowledge_nodes" }o--o| "public.knowledge_nodes" : "FOREIGN KEY (parent_id) REFERENCES knowledge_nodes(id) ON DELETE SET NULL"
"public.knowledge_node_relations" }o--|| "public.knowledge_nodes" : "FOREIGN KEY (source_node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE"
"public.knowledge_node_relations" }o--|| "public.knowledge_nodes" : "FOREIGN KEY (target_node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE"
"public.document_chunks" }o--o| "public.knowledge_nodes" : "FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE SET NULL"
"public.ai_diagnoses" }o--o| "public.knowledge_nodes" : "FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE SET NULL"
"public.student_knowledge_progress" }o--|| "public.knowledge_nodes" : "FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE"
"public.spaced_repetitions" }o--o| "public.knowledge_nodes" : "FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE"
"public.ai_quiz_generations" }o--o| "public.knowledge_nodes" : "FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE"
"public.flashcards" }o--|| "public.knowledge_nodes" : "FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE CASCADE"

"public.knowledge_nodes" {
  bigint id
  bigint course_id
  bigint parent_id FK
  varchar_255_ name
  varchar_255_ name_vi
  varchar_255_ name_en
  text description
  integer level
  integer order_index
  bigint source_content_id
  text source_content_title
  boolean auto_generated
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
"public.knowledge_node_relations" {
  bigint id
  bigint course_id
  bigint source_node_id FK
  bigint target_node_id FK
  varchar_30_ relation_type
  double_precision strength
  boolean auto_generated
  timestamp_without_time_zone created_at
}
"public.document_chunks" {
  bigint id
  bigint node_id FK
  bigint content_id
  bigint course_id
  text chunk_text
  integer chunk_index
  varchar_64_ chunk_hash
  varchar_64_ embedding_model
  varchar_20_ source_type
  integer page_number
  integer start_time_sec
  integer end_time_sec
  varchar_10_ language
  varchar_20_ status
  timestamp_without_time_zone created_at
}
"public.ai_diagnoses" {
  bigint id
  bigint student_id
  bigint attempt_id
  bigint question_id
  bigint node_id FK
  text wrong_answer
  text correct_answer
  text explanation
  varchar_50_ gap_type
  text knowledge_gap
  text study_suggestion
  jsonb suggested_docs_json
  double_precision confidence
  bigint source_chunk_id FK
  varchar_10_ language
  timestamp_without_time_zone created_at
}
"public.student_knowledge_progress" {
  bigint id
  bigint student_id
  bigint node_id FK
  bigint course_id
  integer total_attempts
  integer correct_count
  integer wrong_count
  double_precision mastery_level
  timestamp_without_time_zone last_tested_at
  timestamp_without_time_zone updated_at
}
"public.spaced_repetitions" {
  bigint id
  bigint student_id
  bigint question_id
  bigint node_id FK
  bigint course_id
  double_precision easiness_factor
  integer interval_days
  integer repetitions
  integer quality_last
  date next_review_date
  timestamp_without_time_zone last_reviewed_at
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
"public.ai_quiz_generations" {
  bigint id
  bigint node_id FK
  bigint course_id
  bigint created_by
  varchar_20_ bloom_level
  text question_text
  varchar_50_ question_type
  jsonb answer_options
  text correct_answer
  text explanation
  text source_quote
  bigint source_chunk_id FK
  varchar_10_ language
  varchar_20_ status
  text review_note
  bigint reviewed_by
  timestamp_without_time_zone reviewed_at
  bigint quiz_question_id
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
"public.flashcards" {
  bigint id
  bigint course_id
  bigint node_id FK
  bigint student_id
  text front_text
  text back_text
  bigint source_diagnosis_id FK
  varchar_20_ status
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
