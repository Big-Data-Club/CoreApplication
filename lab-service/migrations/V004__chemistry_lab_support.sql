-- V004__chemistry_lab_support.sql
-- Migration to support CHEMISTRY domain in virtual labs foundation.

-- 1. Update labs.lab_type check constraint
ALTER TABLE labs DROP CONSTRAINT IF EXISTS labs_lab_type_check;
ALTER TABLE labs ADD CONSTRAINT labs_lab_type_check CHECK (lab_type IN (
    'CODING', 'HPC', 'JUPYTER', 'WORKSPACE', 'DATABASE', 'CUSTOM',
    'PLANT', 'ROBOT', 'CHEMISTRY'
));

-- 2. Update experiment_definitions.domain check constraint
ALTER TABLE experiment_definitions DROP CONSTRAINT IF EXISTS experiment_definitions_domain_check;
ALTER TABLE experiment_definitions ADD CONSTRAINT experiment_definitions_domain_check CHECK (domain IN (
    'PLANT', 'ROBOT', 'CHEMISTRY'
));
