# public.quizzes

## Columns

| Name | Type | Default | Nullable | Children | Parents | Comment |
| ---- | ---- | ------- | -------- | -------- | ------- | ------- |
| id | bigint | nextval('quizzes_id_seq'::regclass) | false | [public.quiz_questions](public.quiz_questions.md) [public.quiz_attempts](public.quiz_attempts.md) [public.quiz_analytics](public.quiz_analytics.md) |  |  |
| content_id | bigint |  | false |  | [public.section_content](public.section_content.md) |  |
| title | varchar(500) |  | false |  |  |  |
| description | text |  | true |  |  |  |
| instructions | text |  | true |  |  |  |
| time_limit_minutes | integer |  | true |  |  |  |
| available_from | timestamp without time zone |  | true |  |  |  |
| available_until | timestamp without time zone |  | true |  |  |  |
| max_attempts | integer | 1 | true |  |  |  |
| shuffle_questions | boolean | false | true |  |  |  |
| shuffle_answers | boolean | false | true |  |  |  |
| passing_score | numeric(5,2) |  | true |  |  |  |
| total_points | numeric(10,2) | 100.00 | true |  |  |  |
| auto_grade | boolean | true | true |  |  |  |
| show_results_immediately | boolean | true | true |  |  |  |
| show_correct_answers | boolean | true | true |  |  |  |
| allow_review | boolean | true | true |  |  |  |
| show_feedback | boolean | true | true |  |  |  |
| is_published | boolean | false | true |  |  |  |
| created_by | bigint |  | false |  | [public.users](public.users.md) |  |
| created_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |
| updated_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |

## Constraints

| Name | Type | Definition |
| ---- | ---- | ---------- |
| quizzes_content_id_not_null | n | NOT NULL content_id |
| quizzes_created_by_not_null | n | NOT NULL created_by |
| quizzes_id_not_null | n | NOT NULL id |
| quizzes_title_not_null | n | NOT NULL title |
| quizzes_created_by_fkey | FOREIGN KEY | FOREIGN KEY (created_by) REFERENCES users(id) |
| quizzes_content_id_fkey | FOREIGN KEY | FOREIGN KEY (content_id) REFERENCES section_content(id) ON DELETE CASCADE |
| quizzes_pkey | PRIMARY KEY | PRIMARY KEY (id) |

## Indexes

| Name | Definition |
| ---- | ---------- |
| quizzes_pkey | CREATE UNIQUE INDEX quizzes_pkey ON public.quizzes USING btree (id) |
| idx_quizzes_content | CREATE INDEX idx_quizzes_content ON public.quizzes USING btree (content_id) |
| idx_quizzes_published | CREATE INDEX idx_quizzes_published ON public.quizzes USING btree (is_published) |
| idx_quizzes_available | CREATE INDEX idx_quizzes_available ON public.quizzes USING btree (available_from, available_until) |

## Triggers

| Name | Definition |
| ---- | ---------- |
| update_quizzes_updated_at | CREATE TRIGGER update_quizzes_updated_at BEFORE UPDATE ON public.quizzes FOR EACH ROW EXECUTE FUNCTION update_updated_at_column() |

## Relations

```mermaid
erDiagram

"public.quiz_questions" }o--|| "public.quizzes" : "FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE"
"public.quiz_attempts" }o--|| "public.quizzes" : "FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE"
"public.quiz_analytics" }o--|| "public.quizzes" : "FOREIGN KEY (quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE"
"public.quizzes" }o--|| "public.section_content" : "FOREIGN KEY (content_id) REFERENCES section_content(id) ON DELETE CASCADE"
"public.quizzes" }o--|| "public.users" : "FOREIGN KEY (created_by) REFERENCES users(id)"

"public.quizzes" {
  bigint id
  bigint content_id FK
  varchar_500_ title
  text description
  text instructions
  integer time_limit_minutes
  timestamp_without_time_zone available_from
  timestamp_without_time_zone available_until
  integer max_attempts
  boolean shuffle_questions
  boolean shuffle_answers
  numeric_5_2_ passing_score
  numeric_10_2_ total_points
  boolean auto_grade
  boolean show_results_immediately
  boolean show_correct_answers
  boolean allow_review
  boolean show_feedback
  boolean is_published
  bigint created_by FK
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
"public.quiz_questions" {
  bigint id
  bigint quiz_id FK
  varchar_50_ question_type
  text question_text
  text question_html
  text explanation
  numeric_10_2_ points
  integer order_index
  jsonb settings
  boolean is_required
  bigint node_id
  varchar_20_ bloom_level
  bigint reference_chunk_id
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
"public.quiz_attempts" {
  bigint id
  bigint quiz_id FK
  bigint student_id FK
  integer attempt_number
  timestamp_without_time_zone started_at
  timestamp_without_time_zone submitted_at
  integer time_spent_seconds
  numeric_10_2_ total_points
  numeric_10_2_ earned_points
  numeric_5_2_ percentage
  boolean is_passed
  varchar_20_ status
  timestamp_without_time_zone auto_graded_at
  timestamp_without_time_zone manually_graded_at
  bigint graded_by FK
  varchar_45_ ip_address
  text user_agent
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
"public.quiz_analytics" {
  bigint id
  bigint quiz_id FK
  bigint question_id FK
  integer total_attempts
  integer correct_count
  integer incorrect_count
  numeric_5_2_ average_score
  varchar_20_ difficulty_rating
  timestamp_without_time_zone updated_at
}
"public.section_content" {
  bigint id
  bigint section_id FK
  varchar_50_ type
  varchar_255_ title
  text description
  integer order_index
  jsonb metadata
  boolean is_published
  boolean is_mandatory
  varchar_1000_ file_path
  bigint file_size
  varchar_100_ file_type
  varchar_20_ ai_index_status
  bigint ai_index_job_id
  timestamp_without_time_zone ai_indexed_at
  varchar_64_ embedding_model
  bigint created_by FK
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
"public.users" {
  bigint id
  varchar_255_ email
  varchar_255_ full_name
  timestamp_without_time_zone created_at
  timestamp_without_time_zone updated_at
}
```

---

> Generated by [tbls](https://github.com/k1LoW/tbls)
