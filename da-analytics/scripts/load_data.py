"""
load_data.py
============
Utility functions for loading BDC Lakehouse data into pandas DataFrames.

Supports two access modes:
  1. Direct Parquet file reads from the shared volume.
  2. Live DuckDB connection to the student_analytics.duckdb file.
  3. REST API calls to the personalize-service endpoints.

Usage:
    from scripts.load_data import load_gold_table, load_duckdb_view, load_via_api
"""

import os
import pandas as pd
import duckdb
import requests
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GOLD_DIR = os.environ.get("BDC_GOLD_DIR", "./data/lakehouse/gold")
DUCKDB_PATH = os.environ.get("BDC_DUCKDB_PATH", "./data/student_analytics.duckdb")
API_BASE = os.environ.get("BDC_API_BASE", "http://localhost:8085")
AI_SECRET = os.environ.get("AI_SECRET", "")

GOLD_TABLES = [
    "gold_student_course_metrics",
    "gold_concept_struggles",
    "gold_user_item_matrix",
    "gold_struggle_alerts",
    "gold_study_recommendations",
]


# ---------------------------------------------------------------------------
# Method A: Parquet reads
# ---------------------------------------------------------------------------

def load_gold_table(table_name: str) -> pd.DataFrame:
    """
    Load a Gold layer table from a Parquet export.

    Parameters
    ----------
    table_name : str
        One of the GOLD_TABLES constants, e.g. 'gold_user_item_matrix'.

    Returns
    -------
    pd.DataFrame
    """
    path = os.path.join(GOLD_DIR, f"{table_name}.parquet")
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Parquet file not found: {path}\n"
            "Run the export endpoint first:\n"
            "  curl -X POST -H 'X-AI-Secret: <secret>' "
            "http://localhost:8085/personalize/analytics/gold/export"
        )
    return pd.read_parquet(path)


def load_all_gold_tables() -> dict[str, pd.DataFrame]:
    """Load all Gold Parquet tables and return as a dict keyed by table name."""
    return {name: load_gold_table(name) for name in GOLD_TABLES}


# ---------------------------------------------------------------------------
# Method B: DuckDB direct connection
# ---------------------------------------------------------------------------

def load_duckdb_view(query: str, db_path: Optional[str] = None) -> pd.DataFrame:
    """
    Execute a SQL query against the DuckDB database file.

    Parameters
    ----------
    query : str
        SQL query string. Can reference any view or table in student_analytics.duckdb.
    db_path : str, optional
        Path to the DuckDB file. Defaults to DUCKDB_PATH env variable.

    Returns
    -------
    pd.DataFrame

    Examples
    --------
    >>> df = load_duckdb_view("SELECT * FROM unified_interactions")
    >>> df = load_duckdb_view("SELECT * FROM gold_concept_struggles WHERE user_id = 42")
    """
    path = db_path or DUCKDB_PATH
    conn = duckdb.connect(path, read_only=True)
    try:
        df = conn.execute(query).df()
    finally:
        conn.close()
    return df


def load_unified_interactions(db_path: Optional[str] = None) -> pd.DataFrame:
    """
    Load the complete unified interaction history (DuckDB + Parquet) using the
    unified_interactions Silver view. This is the primary dataset for model training.
    """
    return load_duckdb_view("SELECT * FROM unified_interactions ORDER BY created_at ASC", db_path)


# ---------------------------------------------------------------------------
# Method C: REST API access
# ---------------------------------------------------------------------------

def _api_headers() -> dict:
    if not AI_SECRET:
        raise EnvironmentError(
            "AI_SECRET environment variable is not set. "
            "Export it with: export AI_SECRET='<your-x-ai-secret>'"
        )
    return {"X-AI-Secret": AI_SECRET}


def load_via_api(endpoint: str) -> pd.DataFrame:
    """
    Load data from a personalize-service REST API endpoint.

    Parameters
    ----------
    endpoint : str
        Relative path, e.g. '/personalize/analytics/gold/interaction-matrix'.

    Returns
    -------
    pd.DataFrame
    """
    url = f"{API_BASE}{endpoint}"
    resp = requests.get(url, headers=_api_headers(), timeout=30)
    resp.raise_for_status()
    return pd.DataFrame(resp.json())


def trigger_export() -> dict:
    """Trigger the server-side Gold Parquet export and return the file paths."""
    url = f"{API_BASE}/personalize/analytics/gold/export"
    resp = requests.post(url, headers=_api_headers(), timeout=60)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def build_user_item_matrix(df_matrix: pd.DataFrame):
    """
    Pivot the gold_user_item_matrix DataFrame into a dense user-item affinity matrix.

    Returns
    -------
    pivot_df : pd.DataFrame, shape (n_users, n_items)
        Rows = user_id, Columns = node_id, Values = implicit_affinity_score.
    """
    return (
        df_matrix
        .pivot(index="user_id", columns="node_id", values="implicit_affinity_score")
        .fillna(0.0)
    )


def train_test_split_temporal(df: pd.DataFrame, test_frac: float = 0.2):
    """
    Perform a temporal train/test split on an interaction DataFrame.
    The most recent (test_frac * 100)% of interactions per user form the test set.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns: user_id, created_at, node_id.
    test_frac : float
        Fraction of interactions per user to put in the test set.

    Returns
    -------
    train_df, test_df : (pd.DataFrame, pd.DataFrame)
    """
    df = df.sort_values(["user_id", "created_at"])
    df["rank"] = df.groupby("user_id").cumcount(ascending=False)
    df["total"] = df.groupby("user_id")["user_id"].transform("count")
    test_mask = df["rank"] < (df["total"] * test_frac).astype(int)
    return df[~test_mask].drop(columns=["rank", "total"]), df[test_mask].drop(columns=["rank", "total"])
