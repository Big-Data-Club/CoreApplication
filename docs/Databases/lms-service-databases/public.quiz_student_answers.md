# public.quiz_student_answers

## Columns

| Name | Type | Default | Nullable | Children | Parents | Comment |
| ---- | ---- | ------- | -------- | -------- | ------- | ------- |
| id | bigint | nextval('quiz_student_answers_id_seq'::regclass) | false |  |  |  |
| attempt_id | bigint |  | false |  | [public.quiz_attempts](public.quiz_attempts.md) |  |
| question_id | bigint |  | false |  | [public.quiz_questions](public.quiz_questions.md) |  |
| answer_data | jsonb |  | false |  |  |  |
| points_earned | numeric(10,2) |  | true |  |  |  |
| is_correct | boolean |  | true |  |  |  |
| grader_feedback | text |  | true |  |  |  |
| graded_by | bigint |  | true |  | [public.users](public.users.md) |  |
| graded_at | timestamp without time zone |  | true |  |  |  |
| answered_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |
| time_spent_seconds | integer |  | true |  |  |  |
| created_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |
| updated_at | timestamp without time zone | CURRENT_TIMESTAMP | true |  |  |  |

## Constraints

| Name | Type | Definition |
| ---- | ---- | ---------- |
| quiz_student_answers_answer_data_not_null | n | NOT NULL answer_data |
| quiz_student_answers_attempt_id_not_null | n | NOT NULL attempt_id |
| quiz_student_answers_id_not_null | n | NOT NULL id |
| quiz_student_answers_question_id_not_null | n | NOT NULL question_id |
| quiz_student_answers_graded_by_fkey | FOREIGN KEY | FOREIGN KEY (graded_by) REFERENCES users(id) |
| quiz_student_answers_question_id_fkey | FOREIGN KEY | FOREIGN KEY (question_id) REFERENCES quiz_questions(id) ON DELETE CASCADE |
| quiz_student_answers_attempt_id_fkey | FOREIGN KEY | FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id) ON DELETE CASCADE |
| quiz_student_answers_pkey | PRIMARY KEY | PRIMARY KEY (id) |
| quiz_student_answers_attempt_id_question_id_key | UNIQUE | UNIQUE (attempt_id, question_id) |

## Indexes

| Name | Definition |
| ---- | ---------- |
| quiz_student_answers_pkey | CREATE UNIQUE INDEX quiz_student_answers_pkey ON public.quiz_student_answers USING btree (id) |
| quiz_student_answers_attempt_id_question_id_key | CREATE UNIQUE INDEX quiz_student_answers_attempt_id_question_id_key ON public.quiz_student_answers USING btree (attempt_id, question_id) |
| idx_student_answers_attempt | CREATE INDEX idx_student_answers_attempt ON public.quiz_student_answers USING btree (attempt_id) |
| idx_student_answers_question | CREATE INDEX idx_student_answers_question ON public.quiz_student_answers USING btree (question_id) |
| idx_student_answers_data | CREATE INDEX idx_student_answers_data ON public.quiz_student_answers USING gin (answer_data) |
| idx_student_answers_attempt_grading | CREATE INDEX idx_student_answers_attempt_grading ON public.quiz_student_answers USING btree (attempt_id, is_correct, points_earned) WHERE (is_correct IS NOT NULL) |
| idx_student_answers_ungraded | CREATE INDEX idx_student_answers_ungraded ON public.quiz_student_answers USING btree (attempt_id, question_id) WHERE (points_earned IS NULL) |

## Triggers

| Name | Definition |
| ---- | ---------- |
| update_quiz_student_answers_updated_at | CREATE TRIGGER update_quiz_student_answers_updated_at BEFORE UPDATE ON public.quiz_student_answers FOR EACH ROW EXECUTE FUNCTION update_updated_at_column() |

## Relations

```mermaid
erDiagram

"public.quiz_student_answers" }o--|| "public.quiz_attempts" : "FOREIGN KEY (attempt_id) REFERENCES quiz_attempts(id) ON DELETE CASCADE"
"public.quiz_student_answers" }o--|| "public.quiz_questions" : "FOREIGN KEY (question_id) REFERENCES quiz_questions(id) ON DELETE CASCADE"
"public.quiz_student_answers" }o--o| "public.users" : "FOREIGN KEY (graded_by) REFERENCES users(id)"

"public.quiz_student_answers" {
  bigint id
  bigint attempt_id FK
  bigint question_id FK
  jsonb answer_data
  numeric_10_2_ points_earned
  boolean is_correct
  text grader_feedback
  bigint graded_by FK
  timestamp_without_time_zone graded_at
  timestamp_without_time_zone answered_at
  integer time_spent_seconds
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
