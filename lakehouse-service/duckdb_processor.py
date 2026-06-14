import os
import sys
import logging
from datetime import datetime, timedelta
import click
import duckdb

# Configure logger
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("bdc-lakehouse-processor")

def get_duckdb_connection():
    """Initializes DuckDB with S3/R2 extensions and credentials."""
    con = duckdb.connect(database=':memory:')
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute("INSTALL iceberg; LOAD iceberg;")
    
    # Retrieve configuration from environment
    s3_endpoint = os.getenv("R2_ENDPOINT", "localhost:9000")
    s3_access_key = os.getenv("MINIO_ROOT_USER", "minioadmin")
    s3_secret_key = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
    s3_use_ssl = os.getenv("MINIO_USE_SSL", "false").lower() == "true"
    
    # Configure DuckDB S3 options
    # Clean endpoint prefix if present (e.g. http:// or https://)
    clean_endpoint = s3_endpoint.replace("http://", "").replace("https://", "")
    
    con.execute(f"SET s3_endpoint='{clean_endpoint}';")
    con.execute(f"SET s3_access_key_id='{s3_access_key}';")
    con.execute(f"SET s3_secret_access_key='{s3_secret_key}';")
    con.execute(f"SET s3_use_ssl={'true' if s3_use_ssl else 'false'};")
    con.execute("SET s3_url_style='path';")
    
    return con

@click.command()
@click.option('--date', default=None, help='Target partition date to process in YYYY-MM-DD format (defaults to yesterday)')
@click.option('--bucket', default='lakehouse', help='S3/R2 Bucket name')
def run_etl(date, bucket):
    if not date:
        # Default to yesterday's date to ensure all logs for the day are complete
        date = (datetime.utcnow() - timedelta(days=1)).strftime('%Y-%m-%d')
        
    try:
        dt = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        logger.error(f"Invalid date format: {date}. Must be YYYY-MM-DD.")
        sys.exit(1)
        
    year = dt.strftime('%Y')
    month = dt.strftime('%m')
    day = dt.strftime('%d')
    
    logger.info(f"Starting Lakehouse ETL batch processing for partition: Date={date} (Year={year}, Month={month}, Day={day})")
    
    con = get_duckdb_connection()
    
    # Define S3 prefix paths
    raw_clickstream_prefix = f"s3://{bucket}/raw/clickstream/year={year}/month={month}/day={day}/*.json"
    raw_cdc_quizzes_prefix = f"s3://{bucket}/raw/cdc_lms_quizzes/year={year}/month={month}/day={day}/*.json"
    
    silver_interactions_table = f"s3://{bucket}/warehouse/silver/conformed_user_interactions"
    silver_quiz_attempts_table = f"s3://{bucket}/warehouse/silver/lms_quiz_attempts"
    
    # ── Job 1: Process Clickstream to Silver Layer ───────────────────────────
    logger.info("Running Job 1: Ingesting client clickstream...")
    
    # We verify if there are raw files for this partition. DuckDB's glob failing is caught.
    try:
        # Check if clickstream path matches any files, and parse
        con.execute(f"CREATE OR REPLACE TEMP TABLE raw_interactions AS SELECT * FROM read_json_auto('{raw_clickstream_prefix}');")
        
        # Insert or create conformed interactions table
        logger.info(f"Inserting conformed events into Silver layer: {silver_interactions_table}")
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS "{silver_interactions_table}" AS 
            SELECT 
                user_id::INTEGER as user_id,
                event_type::VARCHAR as event_type,
                target_element::VARCHAR as target_element,
                page_url::VARCHAR as page_url,
                timestamp::TIMESTAMP as event_time,
                payload as payload,
                ingest_time::TIMESTAMP as ingest_time,
                '{year}'::VARCHAR as part_year,
                '{month}'::VARCHAR as part_month
            FROM raw_interactions;
        """)
        
        # If the table already existed, append the partition data
        con.execute(f"""
            INSERT INTO "{silver_interactions_table}"
            SELECT 
                user_id::INTEGER,
                event_type::VARCHAR,
                target_element::VARCHAR,
                page_url::VARCHAR,
                timestamp::TIMESTAMP,
                payload,
                ingest_time::TIMESTAMP,
                '{year}',
                '{month}'
            FROM raw_interactions
            WHERE NOT EXISTS (
                SELECT 1 FROM "{silver_interactions_table}" t 
                WHERE t.user_id = raw_interactions.user_id 
                  AND t.event_time = raw_interactions.timestamp::TIMESTAMP
            );
        """)
        logger.info("Job 1 completed successfully.")
        
    except Exception as e:
        logger.warning(f"No clickstream files found or failed to process clickstream for {date}: {e}")

    # ── Job 2: Process CDC Quiz Attempts to Silver Layer ────────────────────
    logger.info("Running Job 2: Processing CDC database mutations...")
    
    try:
        # Read raw CDC logs containing transaction history
        con.execute(f"CREATE OR REPLACE TEMP TABLE raw_cdc AS SELECT * FROM read_json_auto('{raw_cdc_quizzes_prefix}');")
        
        # Deduplicate changes: select latest state for each attempt_id
        con.execute("""
            CREATE OR REPLACE TEMP TABLE deduped_cdc AS 
            SELECT 
                (payload->>'attempt_id')::INTEGER as attempt_id,
                (payload->>'user_id')::INTEGER as user_id,
                (payload->>'quiz_id')::INTEGER as quiz_id,
                (payload->>'score')::DOUBLE as score,
                (payload->>'completed_at')::TIMESTAMP as completed_at,
                (payload->>'op')::VARCHAR as op,
                (payload->>'db_timestamp')::TIMESTAMP as db_timestamp
            FROM raw_cdc
            QUALIFY ROW_NUMBER() OVER(PARTITION BY attempt_id ORDER BY db_timestamp DESC) = 1;
        """)
        
        # Check if the target Silver table exists
        # If not, create it. Otherwise, execute an idempotent UPSERT (MERGE)
        con.execute(f"""
            CREATE TABLE IF NOT EXISTS "{silver_quiz_attempts_table}" AS 
            SELECT attempt_id, user_id, quiz_id, score, completed_at, db_timestamp as updated_at
            FROM deduped_cdc 
            WHERE op != 'D';
        """)
        
        # Run local MERGE via temporary table union (standard DuckDB pattern for object store tables)
        con.execute(f"""
            CREATE OR REPLACE TEMP TABLE merged_state AS
            SELECT 
                COALESCE(s.attempt_id, t.attempt_id) as attempt_id,
                COALESCE(s.user_id, t.user_id) as user_id,
                COALESCE(s.quiz_id, t.quiz_id) as quiz_id,
                COALESCE(s.score, t.score) as score,
                COALESCE(s.completed_at, t.completed_at) as completed_at,
                COALESCE(s.db_timestamp, t.updated_at) as updated_at,
                COALESCE(s.op, 'U') as op
            FROM "{silver_quiz_attempts_table}" t
            FULL OUTER JOIN deduped_cdc s ON t.attempt_id = s.attempt_id;
        """)
        
        # Rewrite the silver table containing current states (excluding deletes)
        con.execute(f"""
            COPY (
                SELECT attempt_id, user_id, quiz_id, score, completed_at, updated_at 
                FROM merged_state 
                WHERE op != 'D'
            ) TO '{silver_quiz_attempts_table}' (FORMAT 'PARQUET');
        """)
        
        logger.info("Job 2 completed successfully.")
        
    except Exception as e:
        logger.warning(f"No CDC files found or failed to process CDC for {date}: {e}")

    logger.info("Lakehouse ETL Batch Completed.")

if __name__ == '__main__':
    run_etl()
