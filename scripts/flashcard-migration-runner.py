"""Runtime appended to the emitted migration bundle; executed inside AI pod."""
import asyncio
import hashlib
import os
import asyncpg


async def apply(conn, migrations):
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(781605182)")
        await conn.execute("""CREATE TABLE IF NOT EXISTS flashcard_schema_migrations
            (version text PRIMARY KEY, checksum text NOT NULL, applied_at timestamptz NOT NULL DEFAULT now())""")
        for migration in migrations:
            version = migration["version"]
            checksum = hashlib.sha256(migration["sql"].encode()).hexdigest()
            recorded = await conn.fetchval("SELECT checksum FROM flashcard_schema_migrations WHERE version=$1", version)
            if recorded:
                if recorded != checksum:
                    raise RuntimeError("Previously applied migration changed: " + version)
                continue
            present = []
            for table, columns in migration["columns"].items():
                for column in columns:
                    present.append(await conn.fetchval("""SELECT EXISTS(SELECT 1 FROM information_schema.columns
                        WHERE table_schema=current_schema() AND table_name=$1 AND column_name=$2)""", table, column))
            if any(present) and not all(present):
                raise RuntimeError("Partial schema detected; repair before rollout: " + version)
            if not all(present):
                await conn.execute(migration["sql"])
                print("Applied", version)
            else:
                print("Adopted existing", version)
            await conn.execute("INSERT INTO flashcard_schema_migrations(version,checksum) VALUES($1,$2)", version, checksum)


async def main():
    conn = await asyncpg.connect(host=os.environ["AI_DB_HOST"], port=int(os.environ.get("AI_DB_PORT", "5432")), user=os.environ["AI_DB_USER"], password=os.environ["AI_DB_PASSWORD"], database=os.environ["AI_DB_NAME"])
    try:
        await apply(conn, MIGRATIONS)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
