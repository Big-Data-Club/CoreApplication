"""
train_bkt.py
============
Bayesian Knowledge Tracing (BKT) training script using pyBKT.

BKT models student knowledge as a latent binary state (Known / Not Known) using
a Hidden Markov Model (HMM). Four parameters govern the model per skill:

  - P(L0)  : Prior probability the student already knows the skill.
  - P(T)   : Probability of transitioning from Not Known to Known after practice.
  - P(G)   : Probability of guessing correctly despite not knowing (Guess rate).
  - P(S)   : Probability of answering incorrectly despite knowing (Slip rate).

Reference: DATA_ANALYST_RECOMMENDER_GUIDE.md, Section 8, Step 2.

Usage:
    python scripts/train_bkt.py --output output/slates/bkt_mastery.csv
"""

import argparse
import os
import pandas as pd

try:
    from pyBKT.models import Model
except ImportError:
    raise ImportError("pyBKT is not installed. Run: pip install pyBKT")

from scripts.load_data import load_gold_table, load_duckdb_view


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def prepare_bkt_dataset(df_interactions: pd.DataFrame) -> pd.DataFrame:
    """
    Transform raw interaction data into the format expected by pyBKT.

    pyBKT requires columns:
      - user_id   : student identifier
      - skill_name: the knowledge concept / node being practiced
      - correct   : 1 if the response was correct, 0 otherwise

    Parameters
    ----------
    df_interactions : pd.DataFrame
        unified_interactions schema with columns: user_id, node_id, action_type.

    Returns
    -------
    pd.DataFrame with columns [user_id, skill_name, correct]
    """
    # Filter to Quick Check events only
    check_events = df_interactions[
        df_interactions["action_type"].isin(["quick_check_correct", "quick_check_incorrect"])
    ].copy()

    check_events["correct"] = (
        check_events["action_type"] == "quick_check_correct"
    ).astype(int)

    check_events = check_events.rename(columns={"node_id": "skill_name"})
    check_events["skill_name"] = "concept_" + check_events["skill_name"].astype(str)

    return check_events[["user_id", "skill_name", "correct"]].dropna()


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_bkt(df_bkt: pd.DataFrame, num_fits: int = 5, seed: int = 42) -> Model:
    """
    Fit a BKT model to the prepared dataset.

    Parameters
    ----------
    df_bkt : pd.DataFrame
        Dataset with columns [user_id, skill_name, correct].
    num_fits : int
        Number of random restarts for the EM algorithm.
    seed : int
        Random seed for reproducibility.

    Returns
    -------
    Fitted pyBKT Model.
    """
    model = Model(seed=seed, num_fits=num_fits)
    model.fit(data=df_bkt)
    return model


# ---------------------------------------------------------------------------
# Output: mastery scores per student-concept pair
# ---------------------------------------------------------------------------

def extract_mastery_scores(model: Model, df_bkt: pd.DataFrame) -> pd.DataFrame:
    """
    Run model predictions to extract the final mastery probability for each
    (user_id, skill_name) pair at the last observed practice opportunity.

    Returns
    -------
    pd.DataFrame with columns [user_id, skill_name, mastery_prob]
    """
    preds = model.predict(data=df_bkt)
    # pyBKT predict returns state_predictions column (P(mastery) after each step)
    # Take the last observation per user-skill pair
    last_obs = (
        preds
        .sort_values(["user_id", "skill_name"])
        .groupby(["user_id", "skill_name"])
        .tail(1)[["user_id", "skill_name", "state_predictions"]]
        .rename(columns={"state_predictions": "mastery_prob"})
        .reset_index(drop=True)
    )
    return last_obs


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(output_path: str, db_path: str | None = None):
    print("[BKT] Loading interaction data...")
    try:
        df_interactions = load_duckdb_view(
            "SELECT user_id, node_id, action_type, created_at FROM unified_interactions",
            db_path=db_path,
        )
    except Exception:
        print("[BKT] DuckDB unavailable. Falling back to Parquet...")
        df_interactions = load_gold_table("gold_user_item_matrix")

    print(f"[BKT] Total interactions loaded: {len(df_interactions)}")
    df_bkt = prepare_bkt_dataset(df_interactions)
    print(f"[BKT] Quick Check events for BKT: {len(df_bkt)}")

    if df_bkt.empty:
        print("[BKT] No Quick Check events found. Exiting.")
        return

    print("[BKT] Fitting model...")
    model = train_bkt(df_bkt)

    print("[BKT] Learned parameters:")
    print(model.params().to_string())

    print("[BKT] Extracting mastery scores...")
    df_mastery = extract_mastery_scores(model, df_bkt)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    df_mastery.to_csv(output_path, index=False)
    print(f"[BKT] Mastery scores written to: {output_path}")
    print(df_mastery.describe())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train BKT cognitive mastery model")
    parser.add_argument(
        "--output",
        default="output/slates/bkt_mastery.csv",
        help="Output CSV path for mastery scores",
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Path to student_analytics.duckdb (overrides env BDC_DUCKDB_PATH)",
    )
    args = parser.parse_args()
    main(args.output, args.db_path)
