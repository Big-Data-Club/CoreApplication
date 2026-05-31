package main

import (
	"database/sql"
	"fmt"
	"log"
	"os"
	"strings"

	"github.com/joho/godotenv"
	_ "github.com/lib/pq"
)

func main() {
	// Load environment variables from root directory .env
	err := godotenv.Load("../.env")
	if err != nil {
		log.Println("Could not load ../.env, attempting to load local .env")
		_ = godotenv.Load()
	}

	// 1. Connection Configurations
	host := getEnv("POSTGRES_HOST", "localhost")
	user := getEnv("POSTGRES_USER", "postgres")
	pass := getEnv("POSTGRES_PASSWORD", "123456")
	sslMode := "require"

	authDBName := getEnv("POSTGRES_DB", "club_db")
	labDBName := getEnv("LAB_POSTGRES_DB", "lab_db")
	labHost := getEnv("LAB_POSTGRES_HOST", host)
	labUser := getEnv("LAB_POSTGRES_USER", user)
	labPass := getEnv("LAB_POSTGRES_PASSWORD", pass)

	// In local dev, port or host might differ, but we'll use active env
	authDSN := fmt.Sprintf("host=%s port=5432 user=%s password=%s dbname=%s sslmode=%s", host, user, pass, authDBName, sslMode)
	labDSN := fmt.Sprintf("host=%s port=5432 user=%s password=%s dbname=%s sslmode=%s", labHost, labUser, labPass, labDBName, sslMode)

	log.Printf("Connecting to Auth DB: %s (Host: %s)\n", authDBName, host)
	authDB, err := sql.Open("postgres", authDSN)
	if err != nil {
		log.Fatalf("Failed to open Auth DB: %v", err)
	}
	defer authDB.Close()
	if err := authDB.Ping(); err != nil {
		log.Fatalf("Failed to ping Auth DB: %v", err)
	}

	log.Printf("Connecting to Lab DB: %s (Host: %s)\n", labDBName, labHost)
	labDB, err := sql.Open("postgres", labDSN)
	if err != nil {
		log.Fatalf("Failed to open Lab DB: %v", err)
	}
	defer labDB.Close()
	if err := labDB.Ping(); err != nil {
		log.Fatalf("Failed to ping Lab DB: %v", err)
	}

	// 2. Fetch users from Auth and copy/sync them to Lab
	log.Println("Fetching users from Auth DB...")
	rows, err := authDB.Query("SELECT id, email, name, role, active FROM users")
	if err != nil {
		log.Fatalf("Failed to query Auth users: %v", err)
	}
	defer rows.Close()

	var adminUserID int64 = 0
	userCount := 0

	for rows.Next() {
		var id int64
		var email, name, role string
		var active bool
		if err := rows.Scan(&id, &email, &name, &role, &active); err != nil {
			log.Fatalf("Failed to scan Auth user row: %v", err)
		}

		// Convert Spring Boot Roles into text array for Lab Go backend
		rolesList := []string{role}
		// If they have standard roles, map them
		if strings.Contains(strings.ToUpper(role), "ADMIN") {
			rolesList = append(rolesList, "ADMIN", "TEACHER")
		} else if strings.Contains(strings.ToUpper(role), "TEACHER") {
			rolesList = append(rolesList, "TEACHER")
		} else {
			rolesList = append(rolesList, "STUDENT")
		}

		// Format roles array as PostgreSQL literal: {"ROLE1","ROLE2"}
		rolesLiteral := fmt.Sprintf(`{"%s"}`, strings.Join(rolesList, `","`))

		_, err = labDB.Exec(`
			INSERT INTO users (id, email, full_name, roles, is_active, synced_at)
			VALUES ($1, $2, $3, $4, $5, NOW())
			ON CONFLICT (id) DO UPDATE SET
				email = EXCLUDED.email,
				full_name = EXCLUDED.full_name,
				roles = EXCLUDED.roles,
				is_active = EXCLUDED.is_active,
				synced_at = NOW()`,
			id, email, name, rolesLiteral, active)

		if err != nil {
			log.Fatalf("Failed to sync user %s to Lab DB: %v", email, err)
		}

		if strings.Contains(strings.ToUpper(role), "ADMIN") && adminUserID == 0 {
			adminUserID = id
		}
		userCount++
	}

	log.Printf("Successfully synced %d users to Lab DB.\n", userCount)

	// If no admin user was found, insert a dummy one so seeds don't fail foreign keys
	if adminUserID == 0 {
		adminUserID = 1
		log.Println("No ADMIN found in Auth DB. Inserting dummy user ID = 1 for seeding...")
		_, err = labDB.Exec(`
			INSERT INTO users (id, email, full_name, roles, is_active, synced_at)
			VALUES (1, 'admin@hpc.vn', 'BDC Admin', '{"ADMIN", "TEACHER"}', true, NOW())
			ON CONFLICT (id) DO NOTHING`)
		if err != nil {
			log.Fatalf("Failed to insert dummy admin: %v", err)
		}
	}

	// 3. Create an Environment Template
	log.Println("Seeding environment templates...")
	var templateID int64
	err = labDB.QueryRow(`
		INSERT INTO environment_templates (name, description, compute_backend, docker_image, cpu_milli, memory_mb, gpu_count, disk_size_mb, allowed_ports, startup_script, packages, created_by, is_public, created_at, updated_at)
		VALUES ('Default CodeRunner Container', 'Sandbox container equipped with Python, GCC, G++, Java, and Go runtimes for compiling solutions.', 'K8S', 'phucnhan2809/code-runner:latest', 500, 512, 0, 1024, '[]', '', '[]', $1, true, NOW(), NOW())
		RETURNING id`, adminUserID).Scan(&templateID)

	if err != nil {
		// Try to fetch existing
		err = labDB.QueryRow("SELECT id FROM environment_templates WHERE name = 'Default CodeRunner Container' LIMIT 1").Scan(&templateID)
		if err != nil {
			log.Fatalf("Failed to seed environment template: %v", err)
		}
	}
	log.Printf("Environment template set (ID = %d).\n", templateID)

	// 4. Seed Labs
	log.Println("Seeding sample Labs...")

	// Lab 1: Python Sum Array (CODING)
	var lab1ID int64
	err = labDB.QueryRow(`
		INSERT INTO labs (title, description, category, level, thumbnail_url, lab_type, status, runtime_config, environment_template_id, max_session_duration_min, max_concurrent_sessions, max_submissions, auto_grade, grading_config, created_by, published_at, created_at, updated_at)
		VALUES ($1, $2, 'Programming', 'BEGINNER', '', 'CODING', 'PUBLISHED', '{}', $3, 120, 50, 100, true, '{"method": "test_cases"}', $4, NOW(), NOW(), NOW())
		RETURNING id`, "Sum of Elements in Array", "Write a Python function `sum_array(arr)` or read space-separated integers from standard input and print their sum. For example, given the input `5\n1 2 3 4 5`, the output should be `15`.", templateID, adminUserID).Scan(&lab1ID)

	if err != nil {
		log.Printf("Lab 1 already exists or failed: %v. Continuing...\n", err)
	} else {
		log.Printf("Seeded Lab 1: Sum of Elements (ID = %d)\n", lab1ID)
		// Seed Section & Content
		var sec1ID int64
		_ = labDB.QueryRow(`INSERT INTO lab_sections (lab_id, title, description, order_index, is_published) VALUES ($1, 'Instructions', 'Problem specification and constraints', 0, true) RETURNING id`, lab1ID).Scan(&sec1ID)
		if sec1ID > 0 {
			_, _ = labDB.Exec(`INSERT INTO lab_section_content (section_id, type, title, description, order_index, metadata, is_published, is_mandatory, created_by) VALUES ($1, 'TEXT', 'Problem Description', 'Write a program that computes the sum of elements in an array. Input Format: First line contains N (number of elements). Second line contains N integers separated by spaces.', 0, '{}', true, true, $2)`, sec1ID, adminUserID)
		}

		// Seed Test cases
		_, _ = labDB.Exec(`INSERT INTO lab_test_cases (lab_id, name, order_index, is_sample, is_hidden, weight, input, expected, explanation) VALUES ($1, 'Sample Test 1', 0, true, false, 50, E'5\n1 2 3 4 5', E'15\n', '1 + 2 + 3 + 4 + 5 = 15')`, lab1ID)
		_, _ = labDB.Exec(`INSERT INTO lab_test_cases (lab_id, name, order_index, is_sample, is_hidden, weight, input, expected, explanation) VALUES ($1, 'Edge Case Zero', 1, false, false, 50, E'3\n0 0 0', E'0\n', 'Sum of zeros is 0')`, lab1ID)
	}

	// Lab 2: SQL Query Selection (DATABASE)
	var lab2ID int64
	err = labDB.QueryRow(`
		INSERT INTO labs (title, description, category, level, thumbnail_url, lab_type, status, runtime_config, environment_template_id, max_session_duration_min, max_concurrent_sessions, max_submissions, auto_grade, grading_config, created_by, published_at, created_at, updated_at)
		VALUES ($1, $2, 'Database', 'INTERMEDIATE', '', 'DATABASE', 'PUBLISHED', '{}', $3, 120, 50, 100, true, '{"method": "sql_match"}', $4, NOW(), NOW(), NOW())
		RETURNING id`, "SQL Users Audit", "Formulate a SQL query to fetch all active administrators from the database who registered before January 2026, sorted by their creation date in descending order.", templateID, adminUserID).Scan(&lab2ID)

	if err != nil {
		log.Printf("Lab 2 already exists or failed: %v. Continuing...\n", err)
	} else {
		log.Printf("Seeded Lab 2: SQL Users Audit (ID = %d)\n", lab2ID)
		var sec2ID int64
		_ = labDB.QueryRow(`INSERT INTO lab_sections (lab_id, title, description, order_index, is_published) VALUES ($1, 'Task Overview', 'Write query guidelines', 0, true) RETURNING id`, lab2ID).Scan(&sec2ID)
		if sec2ID > 0 {
			_, _ = labDB.Exec(`INSERT INTO lab_section_content (section_id, type, title, description, order_index, metadata, is_published, is_mandatory, created_by) VALUES ($1, 'TEXT', 'Audit Requirements', 'Select the fields id, email, full_name, and roles where roles contains ADMIN, ordered by created_at DESC.', 0, '{}', true, true, $2)`, sec2ID, adminUserID)
		}
	}

	// Lab 3: Ubuntu Terminal IDE (WORKSPACE)
	var lab3ID int64
	err = labDB.QueryRow(`
		INSERT INTO labs (title, description, category, level, thumbnail_url, lab_type, status, runtime_config, environment_template_id, max_session_duration_min, max_concurrent_sessions, max_submissions, auto_grade, grading_config, created_by, published_at, created_at, updated_at)
		VALUES ($1, $2, 'Infrastructure', 'ADVANCED', '', 'WORKSPACE', 'PUBLISHED', '{}', $3, 180, 20, 0, false, '{}', $4, NOW(), NOW(), NOW())
		RETURNING id`, "Linux Terminal & Shell Scripting Sandbox", "A sandbox workspace running an interactive terminal. Practice shell scripting, write custom scripts to process files, and run tasks directly on a dedicated, isolated sandbox container.", templateID, adminUserID).Scan(&lab3ID)

	if err != nil {
		log.Printf("Lab 3 already exists or failed: %v. Continuing...\n", err)
	} else {
		log.Printf("Seeded Lab 3: Linux Terminal Workspace (ID = %d)\n", lab3ID)
		var sec3ID int64
		_ = labDB.QueryRow(`INSERT INTO lab_sections (lab_id, title, description, order_index, is_published) VALUES ($1, 'Sandbox Exercises', 'Interactive tasks to perform in workspace', 0, true) RETURNING id`, lab3ID).Scan(&sec3ID)
		if sec3ID > 0 {
			_, _ = labDB.Exec(`INSERT INTO lab_section_content (section_id, type, title, description, order_index, metadata, is_published, is_mandatory, created_by) VALUES ($1, 'TEXT', 'Console Guide', 'Use the terminal panel to build files, write bash scripts, and interact with the filesystem. Click Start Session to provision a terminal instance.', 0, '{}', true, true, $2)`, sec3ID, adminUserID)
		}
	}

	log.Println("Database Seeding Completed Successfully!")
}

func getEnv(key, fallback string) string {
	if value, exists := os.LookupEnv(key); exists {
		return value
	}
	return fallback
}
