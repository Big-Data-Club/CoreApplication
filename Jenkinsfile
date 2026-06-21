pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
        disableConcurrentBuilds()
        ansiColor('xterm')
    }

    parameters {
        booleanParam(name: 'FORCE_BUILD', defaultValue: false, description: 'Force testing, building, and deploying all services')
        choice(name: 'COMPOSE_FILE', choices: ['docker-compose.serverless.yml', 'docker-compose.yml'], description: 'Choose which Docker Compose configuration to deploy')
    }

    environment {
        // Global variables
        DOCKER_BUILDKIT = '1'
        COMPOSE_DOCKER_CLI_BUILD = '1'
        BDC_ENV_FILE = credentials('bdc-env-file')
    }

    stages {
        stage('Checkout & Submodules') {
            steps {
                echo 'Checking out source code...'
                checkout scm
                
                echo 'Copying environment configuration...'
                sh 'cp "$BDC_ENV_FILE" .env'
                
                echo 'Synchronizing and updating git submodules (frontend)...'
                sh 'git submodule update --init --recursive'
            }
        }

        stage('Detect Changes') {
            steps {
                script {
                    if (params.FORCE_BUILD) {
                        echo 'Force Build enabled. Setting all service change flags to true.'
                        env.AUTH_CHANGED = 'true'
                        env.LMS_CHANGED = 'true'
                        env.CHAT_CHANGED = 'true'
                        env.AI_CHANGED = 'true'
                        env.FRONTEND_CHANGED = 'true'
                        env.DOCKER_CHANGED = 'true'
                        return
                    }

                    // Check if previous successful commit exists, otherwise compare with HEAD~1
                    def sinceCommit = env.GIT_PREVIOUS_SUCCESSFUL_COMMIT ?: "HEAD~1"
                    echo "Analyzing changes between ${sinceCommit} and ${env.GIT_COMMIT}..."

                    // Run git diff to get changed file list
                    def diffOutput = sh(script: "git diff --name-only ${sinceCommit} ${env.GIT_COMMIT}", returnStdout: true).trim()
                    def changedFiles = diffOutput.split("\n")

                    // Reset flags
                    env.AUTH_CHANGED = 'false'
                    env.LMS_CHANGED = 'false'
                    env.CHAT_CHANGED = 'false'
                    env.AI_CHANGED = 'false'
                    env.FRONTEND_CHANGED = 'false'
                    env.DOCKER_CHANGED = 'false'

                    for (file in changedFiles) {
                        if (file.startsWith("auth-and-management-service/")) {
                            env.AUTH_CHANGED = 'true'
                        } else if (file.startsWith("lms-service/")) {
                            env.LMS_CHANGED = 'true'
                        } else if (file.startsWith("chat-service/")) {
                            env.CHAT_CHANGED = 'true'
                        } else if (file.startsWith("ai-service/")) {
                            env.AI_CHANGED = 'true'
                        } else if (file.startsWith("frontend/") || file.equals("frontend")) {
                            env.FRONTEND_CHANGED = 'true'
                        } else if (file.equals("docker-compose.yml") || 
                                   file.equals("docker-compose.serverless.yml") || 
                                   file.equals(".env") || 
                                   file.equals(".env.example")) {
                            env.DOCKER_CHANGED = 'true'
                        }
                    }

                    echo "Change detection report:"
                    echo "  - Auth Service: ${env.AUTH_CHANGED}"
                    echo "  - LMS Service:  ${env.LMS_CHANGED}"
                    echo "  - Chat Service: ${env.CHAT_CHANGED}"
                    echo "  - AI Service:   ${env.AI_CHANGED}"
                    echo "  - Frontend:     ${env.FRONTEND_CHANGED}"
                    echo "  - Docker Setup: ${env.DOCKER_CHANGED}"
                }
            }
        }

        stage('Parallel Tests (CI)') {
            parallel {
                stage('Test Auth') {
                    when { expression { env.AUTH_CHANGED == 'true' } }
                    steps {
                        echo 'Running Auth Service Maven tests inside Eclipse Temurin Docker container...'
                        dir('auth-and-management-service') {
                            sh 'docker run --rm -v "$(pwd)":/app -v "$HOME/.m2":/root/.m2 -w /app maven:3.9-eclipse-temurin-21 mvn clean test'
                        }
                    }
                }

                stage('Test LMS') {
                    when { expression { env.LMS_CHANGED == 'true' } }
                    steps {
                        echo 'Running LMS Service Go tests inside Golang Docker container...'
                        dir('lms-service') {
                            sh 'docker run --rm -v "$(pwd)":/app -w /app golang:1.25-alpine go test ./...'
                        }
                    }
                }

                stage('Test Chat') {
                    when { expression { env.CHAT_CHANGED == 'true' } }
                    steps {
                        echo 'Running Chat Service Go tests inside Golang Docker container...'
                        dir('chat-service') {
                            sh 'docker run --rm -v "$(pwd)":/app -w /app golang:1.25-alpine go test ./...'
                        }
                    }
                }

                stage('Test Frontend') {
                    when { expression { env.FRONTEND_CHANGED == 'true' } }
                    steps {
                        echo 'Running Frontend linting inside Node.js Docker container...'
                        dir('frontend') {
                            sh 'docker run --rm -v "$(pwd)":/app -w /app node:20-alpine sh -c "npm install && npm run lint"'
                        }
                    }
                }
            }
        }

        stage('Build Changed Images') {
            steps {
                script {
                    def file = params.COMPOSE_FILE
                    echo "Building changed service images using ${file}..."

                    if (env.AUTH_CHANGED == 'true') {
                        sh "docker compose -f ${file} build backend"
                    }
                    if (env.LMS_CHANGED == 'true') {
                        sh "docker compose -f ${file} build lms-backend"
                    }
                    if (env.CHAT_CHANGED == 'true') {
                        sh "docker compose -f ${file} build chat-backend"
                    }
                    if (env.AI_CHANGED == 'true') {
                        sh "docker compose -f ${file} build ai-service"
                        sh "docker compose -f ${file} build ai-worker"
                    }
                    if (env.FRONTEND_CHANGED == 'true') {
                        sh "docker compose -f ${file} build frontend"
                    }
                }
            }
        }

        stage('Selective Deploy') {
            steps {
                script {
                    def file = params.COMPOSE_FILE
                    echo "Deploying update on the server using ${file}..."

                    if (env.DOCKER_CHANGED == 'true') {
                        echo "Docker configuration files changed. Re-creating the entire stack..."
                        sh "docker compose -f ${file} up -d"
                    } else {
                        // Recreate only the updated containers
                        if (env.AUTH_CHANGED == 'true') {
                            sh "docker compose -f ${file} up -d --no-deps backend"
                        }
                        if (env.LMS_CHANGED == 'true') {
                            sh "docker compose -f ${file} up -d --no-deps lms-backend"
                        }
                        if (env.CHAT_CHANGED == 'true') {
                            sh "docker compose -f ${file} up -d --no-deps chat-backend"
                        }
                        if (env.AI_CHANGED == 'true') {
                            sh "docker compose -f ${file} up -d --no-deps ai-service ai-worker"
                        }
                        if (env.FRONTEND_CHANGED == 'true') {
                            sh "docker compose -f ${file} up -d --no-deps frontend"
                        }
                    }
                }
            }
        }

        stage('Healthchecks') {
            steps {
                echo 'Running post-deployment healthcheck checks...'
                script {
                    // Try reaching frontend health check
                    sh '''
                        for i in {1..12}; do
                            if curl -f http://localhost:3000/api/health; then
                                echo "Frontend is healthy!"
                                exit 0
                            fi
                            echo "Waiting for Traefik and Frontend to be ready... ($i/12)"
                            sleep 10
                        done
                        echo "Healthcheck timed out!"
                        exit 1
                    '''
                }
            }
        }
    }

    post {
        always {
            echo 'Pipeline execution complete.'
        }
        success {
            echo 'Deployment Succeeded! Cleaning up dangling docker images...'
            sh 'docker image prune -f'
        }
        failure {
            echo 'Deployment Failed. Check build console logs.'
        }
    }
}
