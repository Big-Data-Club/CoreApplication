import sys
import subprocess
import os

# =============================================================================
# 1. Dependency Auto-Installation
# =============================================================================
def install_dependencies():
    required = {'psycopg2-binary', 'bcrypt'}
    installed = set()
    try:
        import psycopg2
        installed.add('psycopg2-binary')
    except ImportError:
        pass
    try:
        import bcrypt
        installed.add('bcrypt')
    except ImportError:
        pass
        
    missing = required - installed
    if missing:
        print(f"Installing missing dependencies: {list(missing)}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("Dependencies installed successfully.")
        except Exception as e:
            print(f"Error installing dependencies: {e}")
            sys.exit(1)

install_dependencies()

import psycopg2
import bcrypt

# =============================================================================
# 2. Parse Environment Variables from .env
# =============================================================================
def load_env(filepath=".env"):
    env = {}
    if not os.path.exists(filepath):
        return env
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, val = line.split('=', 1)
                env[key.strip()] = val.strip()
    return env

env = load_env()

# Get Auth DB configs
AUTH_HOST = env.get("POSTGRES_HOST", "localhost")
AUTH_DB = env.get("POSTGRES_DB", "auth")
AUTH_USER = env.get("POSTGRES_USER", "postgres")
AUTH_PASSWORD = env.get("POSTGRES_PASSWORD", "")
AUTH_PORT = env.get("POSTGRES_PORT", "5433")

# Get LMS DB configs
LMS_HOST = env.get("LMS_POSTGRES_HOST", "localhost")
LMS_DB = env.get("LMS_POSTGRES_DB", "lms")
LMS_USER = env.get("LMS_POSTGRES_USER", "postgres")
LMS_PASSWORD = env.get("LMS_POSTGRES_PASSWORD", "")
LMS_PORT = env.get("LMS_POSTGRES_PORT", "5434")

# =============================================================================
# 3. Database Insertion Logic
# =============================================================================
def main():
    print("Generating BCrypt password hash for 'password'...")
    hashed_pwd = bcrypt.hashpw(b"password", bcrypt.gensalt(10)).decode('utf-8')
    
    users_to_seed = [
        {
            "name": "Test Student",
            "email": "student@example.com",
            "role": "ROLE_USER", # Maps to student in LMS
            "team": "RESEARCH",
            "code": "STUDENT001",
            "type": "STUDENT",
            "lms_role": "STUDENT"
        },
        {
            "name": "Test Teacher",
            "email": "teacher@example.com",
            "role": "ROLE_MANAGER", # Maps to teacher in LMS
            "team": "RESEARCH",
            "code": "TEACHER001",
            "type": "TEACHER",
            "lms_role": "TEACHER"
        },
        {
            "name": "Test Admin",
            "email": "admin@example.com",
            "role": "ROLE_ADMIN",
            "team": "RESEARCH",
            "code": "ADMIN001",
            "type": "ADMIN",
            "lms_role": "ADMIN"
        }
    ]

    # --- Connect to Auth DB ---
    print(f"Connecting to Auth DB ({AUTH_HOST}:{AUTH_PORT}/{AUTH_DB})...")
    try:
        auth_conn = psycopg2.connect(
            host=AUTH_HOST,
            database=AUTH_DB,
            user=AUTH_USER,
            password=AUTH_PASSWORD,
            port=AUTH_PORT
        )
        auth_cur = auth_conn.cursor()
    except Exception as e:
        print(f"Failed to connect to Auth Database: {e}")
        return

    # Seed users into Auth DB and retrieve their IDs
    user_ids = {}
    try:
        # Check constraints or check columns first
        auth_cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users';")
        cols = [r[0] for r in auth_cur.fetchall()]
        print(f"Auth DB user columns: {cols}")

        for u in users_to_seed:
            # Check if user already exists
            auth_cur.execute("SELECT id FROM users WHERE email = %s;", (u["email"],))
            row = auth_cur.fetchone()
            if row:
                uid = row[0]
                print(f"User {u['email']} already exists in Auth DB with ID {uid}. Updating password and role...")
                auth_cur.execute(
                    "UPDATE users SET password = %s, role = %s WHERE id = %s;",
                    (hashed_pwd, u["role"], uid)
                )
                user_ids[u["email"]] = uid
            else:
                print(f"Inserting {u['email']} into Auth DB...")
                auth_cur.execute(
                    """
                    INSERT INTO users (name, email, password, role, team, code, type, active, total_score, auth_provider, pending_approval)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, true, 0, 'LOCAL', false)
                    RETURNING id;
                    """,
                    (u["name"], u["email"], hashed_pwd, u["role"], u["team"], u["code"], u["type"])
                )
                uid = auth_cur.fetchone()[0]
                user_ids[u["email"]] = uid
                print(f"Seeded {u['email']} in Auth DB with ID {uid}")
        
        auth_conn.commit()
    except Exception as e:
        auth_conn.rollback()
        print(f"Error seeding Auth DB: {e}")
        auth_conn.close()
        return
    finally:
        auth_conn.close()

    # --- Connect to LMS DB ---
    print(f"Connecting to LMS DB ({LMS_HOST}:{LMS_PORT}/{LMS_DB})...")
    try:
        lms_conn = psycopg2.connect(
            host=LMS_HOST,
            database=LMS_DB,
            user=LMS_USER,
            password=LMS_PASSWORD,
            port=LMS_PORT
        )
        lms_cur = lms_conn.cursor()
    except Exception as e:
        print(f"Failed to connect to LMS Database: {e}")
        return

    # Seed users into LMS DB
    try:
        for u in users_to_seed:
            uid = user_ids.get(u["email"])
            if not uid:
                continue
                
            lms_cur.execute("SELECT id FROM users WHERE email = %s;", (u["email"],))
            row = lms_cur.fetchone()
            if row:
                print(f"User {u['email']} already exists in LMS DB. Updating role...")
                lms_cur.execute(
                    "UPDATE users SET role = %s, full_name = %s WHERE id = %s;",
                    (u["lms_role"], u["name"], uid)
                )
            else:
                print(f"Inserting {u['email']} with ID {uid} into LMS DB...")
                lms_cur.execute(
                    """
                    INSERT INTO users (id, email, full_name, role, active)
                    VALUES (%s, %s, %s, %s, true);
                    """,
                    (uid, u["email"], u["name"], u["lms_role"])
                )
                print(f"Seeded {u['email']} in LMS DB")
        
        lms_conn.commit()
        print("\nAll test accounts successfully seeded and synchronized!")
    except Exception as e:
        lms_conn.rollback()
        print(f"Error seeding LMS DB: {e}")
    finally:
        lms_conn.close()

if __name__ == "__main__":
    main()
