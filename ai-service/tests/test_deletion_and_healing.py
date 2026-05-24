import asyncio
import os
import sys

# Load the root .env file if it exists to support serverless database testing
root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "../..", ".env"))
if os.path.exists(root_env):
    try:
        from dotenv import load_dotenv
        load_dotenv(root_env)
    except ImportError:
        # Fallback manual parser if python-dotenv is not installed
        with open(root_env, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    os.environ[k] = v

# Map root .env names to config-expected names BEFORE setting defaults
if os.getenv("AI_POSTGRES_HOST"):
    os.environ["AI_DB_HOST"] = os.getenv("AI_POSTGRES_HOST")
if os.getenv("AI_POSTGRES_PORT"):
    os.environ["AI_DB_PORT"] = os.getenv("AI_POSTGRES_PORT")
elif os.getenv("AI_POSTGRES_HOST") and "neon.tech" in os.getenv("AI_POSTGRES_HOST"):
    os.environ["AI_DB_PORT"] = "5432"  # default Neon port

if os.getenv("AI_POSTGRES_USER"):
    os.environ["AI_DB_USER"] = os.getenv("AI_POSTGRES_USER")
if os.getenv("AI_POSTGRES_PASSWORD"):
    os.environ["AI_DB_PASSWORD"] = os.getenv("AI_POSTGRES_PASSWORD")
if os.getenv("AI_POSTGRES_DB"):
    os.environ["AI_DB_NAME"] = os.getenv("AI_POSTGRES_DB")

if os.getenv("NEO4J_USERNAME"):
    os.environ["NEO4J_USER"] = os.getenv("NEO4J_USERNAME")

# Set test environment defaults (used if not set in .env)
os.environ.setdefault("AI_DB_HOST", "localhost")
os.environ.setdefault("AI_DB_PORT", "5435")
os.environ.setdefault("AI_DB_USER", "ai_user")
os.environ.setdefault("AI_DB_PASSWORD", "ai_password")
os.environ.setdefault("AI_DB_NAME", "ai_db")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")
os.environ.setdefault("REDIS_PASSWORD", "redis_password")
os.environ.setdefault("REDIS_DB", "1")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")
os.environ.setdefault("QDRANT_GRPC_PORT", "6334")
os.environ.setdefault("QDRANT_PREFER_GRPC", "false")
os.environ.setdefault("NEO4J_ENABLED", "false")  # Skip Neo4j for basic tests
os.environ.setdefault("USE_QDRANT", "true")
os.environ.setdefault("GROQ_API_KEY", "test")

# Ensure we can import the app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import init_ai_pool, close_ai_pool, get_ai_conn
from app.services.auto_index_service import auto_index_service, ExtractedNode
from app.services.qdrant_service import qdrant_service

async def run_tests():
    print("Initializing DB pool...")
    await init_ai_pool()
    await qdrant_service.init_collections()
    
    course_id = 999111
    content_id = 888111
    
    print("\n--- Test 1: Creating mock nodes & chunks ---")
    # 1. Create a mock node in PostgreSQL
    async with get_ai_conn() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO knowledge_nodes (course_id, name, description, level, source_content_id)
            VALUES ($1, 'Mock OOP Concept', 'Object Oriented Programming principles', 1, $2)
            RETURNING id
            """,
            course_id, content_id
        )
        node_id = row["id"]
        print(f"Created node_id = {node_id}")

        # 2. Insert corresponding chunk in PG
        chunk_row = await conn.fetchrow(
            """
            INSERT INTO document_chunks (content_id, course_id, node_id, chunk_text, chunk_index, chunk_hash, status)
            VALUES ($1, $2, $3, 'OOP means object oriented programming.', 0, 'test-hash-delete', 'ready')
            RETURNING id
            """,
            content_id, course_id, node_id
        )
        chunk_id = chunk_row["id"]
        print(f"Created chunk_id = {chunk_id}")

    # 3. Create point in Qdrant collections
    dummy_vector = [0.1] * 1024
    await qdrant_service.upsert_node(
        node_id=node_id,
        embedding=dummy_vector,
        payload={"course_id": course_id, "name": "Mock OOP Concept", "description": "Object Oriented Programming principles"}
    )
    await qdrant_service.upsert_chunk(
        chunk_id=chunk_id,
        embedding=dummy_vector,
        payload={"course_id": course_id, "content_id": content_id, "node_id": node_id, "chunk_text": "OOP means object oriented programming."}
    )
    print("Upserted points to Qdrant.")

    # Verify they exist
    nodes_scroll = await qdrant_service.scroll_nodes_for_course(course_id)
    assert len(nodes_scroll) == 1
    assert nodes_scroll[0].id == node_id
    print("Verified Qdrant nodes scroll works.")

    print("\n--- Test 2: Course Deletion Cascade ---")
    await auto_index_service.delete_course_data(course_id)
    
    # Check PG
    async with get_ai_conn() as conn:
        kn_rows = await conn.fetch("SELECT id FROM knowledge_nodes WHERE course_id = $1", course_id)
        dc_rows = await conn.fetch("SELECT id FROM document_chunks WHERE course_id = $1", course_id)
        assert len(kn_rows) == 0, f"Expected 0 nodes, got {len(kn_rows)}"
        assert len(dc_rows) == 0, f"Expected 0 chunks, got {len(dc_rows)}"
    print("PG course data successfully deleted.")

    # Check Qdrant
    nodes_scroll = await qdrant_service.scroll_nodes_for_course(course_id)
    assert len(nodes_scroll) == 0, f"Expected 0 nodes in Qdrant, got {len(nodes_scroll)}"
    print("Qdrant course data successfully deleted.")

    print("\n--- Test 3: Self-Healing / Fault Tolerance in _dedup_qdrant ---")
    # Let's create a dangling node in Qdrant (exists in Qdrant but deleted in PG)
    dangling_node_id = 999222
    await qdrant_service.upsert_node(
        node_id=dangling_node_id,
        embedding=dummy_vector,
        payload={"course_id": course_id, "name": "Dangling Concept", "description": "OOP Polymorphism"}
    )
    print("Created dangling node in Qdrant (not in PG).")

    # Scroll nodes and verify it exists in Qdrant
    nodes_scroll = await qdrant_service.scroll_nodes_for_course(course_id)
    assert len(nodes_scroll) == 1
    assert nodes_scroll[0].id == dangling_node_id

    # Call deduplicate_nodes with a new node that matches the dangling node
    # Since it's dangling (not in PG), deduplication should ignore it and treat the new node as TRULY NEW (not reused)
    new_node = ExtractedNode(
        name="Dangling Concept",
        name_vi="Khái niệm treo",
        name_en="Dangling Concept",
        description="OOP Polymorphism",
        keywords=["OOP", "Polymorphism"],
        order_index=0
    )
    
    truly_new_nodes, truly_new_embs, idx_to_existing = await auto_index_service._deduplicate_nodes(
        nodes=[new_node],
        embeddings=[dummy_vector],
        course_id=course_id
    )

    # Assertions
    assert len(truly_new_nodes) == 1, "Should treat new node as truly new, not matching dangling"
    assert len(idx_to_existing) == 0, "Should not reuse the dangling node ID"
    print("Deduplication successfully ignored dangling node.")

    # Wait a tiny bit for the background deletion task to finish
    await asyncio.sleep(0.5)

    # Check Qdrant scroll again: it should have been self-healed and deleted!
    nodes_scroll = await qdrant_service.scroll_nodes_for_course(course_id)
    assert len(nodes_scroll) == 0, f"Expected 0 nodes after self-healing, got {len(nodes_scroll)}"
    print("Self-healing successfully deleted the dangling node from Qdrant!")

    await close_ai_pool()
    await qdrant_service.close()
    print("\nAll integration tests passed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
