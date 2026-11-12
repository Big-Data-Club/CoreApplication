-- Synthetic data only. Loaded into an isolated integration-test schema.
CREATE TABLE users(id bigint PRIMARY KEY,full_name text);
CREATE TABLE quizzes(id bigint PRIMARY KEY,title text);
CREATE TABLE quiz_attempts(id bigint PRIMARY KEY,quiz_id bigint,student_id bigint,attempt_number int,started_at timestamp,submitted_at timestamp,status text,percentage numeric,total_points numeric,earned_points numeric,is_passed boolean,time_spent_seconds int,focus_summary jsonb);
CREATE TABLE quiz_questions(id bigint PRIMARY KEY,quiz_id bigint,question_text text,question_type text,points numeric,order_index int);
CREATE TABLE quiz_answer_options(id bigint PRIMARY KEY,question_id bigint,option_text text,is_correct boolean,order_index int);
CREATE TABLE quiz_correct_answers(id bigint PRIMARY KEY,question_id bigint,answer_text text,blank_id int);
CREATE TABLE quiz_student_answers(id bigint PRIMARY KEY,attempt_id bigint,question_id bigint,points_earned numeric,is_correct boolean,time_spent_seconds int,answer_data jsonb);
INSERT INTO users VALUES(7,'Test learner'); INSERT INTO quizzes VALUES(42,'Test quiz');
INSERT INTO quiz_questions VALUES(1,42,'Question A','SINGLE_CHOICE',10,1),(2,42,'Question B','ESSAY',10,2),(3,42,'Unanswered','ESSAY',10,3);
INSERT INTO quiz_answer_options VALUES(11,1,'Right',true,1),(12,1,'Wrong',false,2);
INSERT INTO quiz_attempts VALUES(1,42,7,1,now(),now(),'GRADED',100,20,20,true,30,'{"departures":2,"away_seconds":5}'),(2,42,7,2,now(),now(),'SUBMITTED',50,20,10,false,60,NULL),(3,42,7,3,now(),NULL,'IN_PROGRESS',NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO quiz_student_answers VALUES(1,1,1,10,true,10,'{"selected_option_id":11}'),(2,1,2,10,true,20,'{"answer_text":"Response"}'),(3,2,1,0,false,10,'{"selected_option_ids":[12,12]}'),(4,2,2,NULL,NULL,15,'{"answer_text":"Pending"}'),(5,3,1,NULL,NULL,10,'{"selected_option_id":11}');
