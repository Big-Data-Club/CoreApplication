# public.document_chunks

## Columns

| Name | Type | Default | Nullable | Children | Parents | Comment |
| ---- | ---- | ------- | -------- | -------- | ------- | ------- |
| id | bigint | nextval('document_chunks_id_seq'::regclass) | false | [public.ai_diagnoses](public.ai_diagnoses.md) [public.ai_quiz_generations](public.ai_quiz_generations.md) |  |  |
| node_id | bigint |  | true |  | [public.knowledge_nodes](public.knowledge_nodes.md) |  |
| content_id | bigint |  | true |  |  |  |
| course_id | bigint |  | false |  |  |  |
| chunk_text | text |  | false |  |  |  |
| chunk_index | integer |  | false |  |  |  |
| chunk_hash | varchar(64) |  | true |  |  |  |
| embedding_model | varchar(64) | 'bge-m3'::character varying | true |  |  |  |
| source_type | varchar(20) | 'document'::character varying | true |  |  |  |
| page_number | integer |  | true |  |  |  |
| start_time_sec | integer |  | true |  |  |  |
| end_time_sec | integer |  | true |  |  |  |
| language | varchar(10) | 'vi'::character varying | true |  |  |  |
| status | varchar(20) | 'ready'::character varying | true |  |  |  |
| created_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |

## Constraints

| Name | Type | Definition |
| ---- | ---- | ---------- |
| document_chunks_chunk_index_not_null | n | NOT NULL chunk_index |
| document_chunks_chunk_text_not_null | n | NOT NULL chunk_text |
| document_chunks_course_id_not_null | n | NOT NULL course_id |
| document_chunks_id_not_null | n | NOT NULL id |
| document_chunks_source_type_check | CHECK | CHECK (((source_type)::text = ANY ((ARRAY['document'::character varying, 'video'::character varying])::text[]))) |
| document_chunks_status_check | CHECK | CHECK (((status)::text = ANY ((ARRAY['pending'::character varying, 'processing'::character varying, 'ready'::character varying, 'error'::character varying])::text[]))) |
| document_chunks_node_id_fkey | FOREIGN KEY | FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE SET NULL |
| document_chunks_pkey | PRIMARY KEY | PRIMARY KEY (id) |
| document_chunks_chunk_hash_key | UNIQUE | UNIQUE (chunk_hash) |

## Indexes

| Name | Definition |
| ---- | ---------- |
| document_chunks_pkey | CREATE UNIQUE INDEX document_chunks_pkey ON public.document_chunks USING btree (id) |
| document_chunks_chunk_hash_key | CREATE UNIQUE INDEX document_chunks_chunk_hash_key ON public.document_chunks USING btree (chunk_hash) |
| idx_dc_content | CREATE INDEX idx_dc_content ON public.document_chunks USING btree (content_id) |
| idx_dc_node | CREATE INDEX idx_dc_node ON public.document_chunks USING btree (node_id) |
| idx_dc_course | CREATE INDEX idx_dc_course ON public.document_chunks USING btree (course_id) |
| idx_dc_status | CREATE INDEX idx_dc_status ON public.document_chunks USING btree (status) |
| idx_dc_hash | CREATE INDEX idx_dc_hash ON public.document_chunks USING btree (chunk_hash) |
| idx_dc_content_status | CREATE INDEX idx_dc_content_status ON public.document_chunks USING btree (content_id, status) |
| idx_dc_node_status | CREATE INDEX idx_dc_node_status ON public.document_chunks USING btree (node_id, status) WHERE (node_id IS NOT NULL) |

## Relations

```mermaid
erDiagram

"public.ai_diagnoses" }o--o| "public.document_chunks" : "FOREIGN KEY (source_chunk_id) REFERENCES document_chunks(id) ON DELETE SET NULL"
"public.ai_quiz_generations" }o--o| "public.document_chunks" : "FOREIGN KEY (source_chunk_id) REFERENCES document_chunks(id) ON DELETE SET NULL"
"public.document_chunks" }o--o| "public.knowledge_nodes" : "FOREIGN KEY (node_id) REFERENCES knowledge_nodes(id) ON DELETE SET NULL"

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
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
