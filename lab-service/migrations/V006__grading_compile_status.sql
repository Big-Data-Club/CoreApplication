-- Runner and submission verdicts use COMPILE_ERROR. Per-case diagnostics must
-- accept the same status so compilation failures are stored atomically.
ALTER TABLE submission_test_results
    DROP CONSTRAINT IF EXISTS submission_test_results_status_check;

ALTER TABLE submission_test_results
    ADD CONSTRAINT submission_test_results_status_check CHECK (status IN (
        'PENDING', 'PASSED', 'WRONG_ANSWER', 'TIME_LIMIT',
        'MEMORY_LIMIT', 'RUNTIME_ERROR', 'COMPILE_ERROR'
    ));
