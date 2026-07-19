"""
metrics.py
==========
Reference implementation of all offline evaluation metrics used to benchmark
recommender models against the BDC heuristic baseline.

Metrics implemented:
  - Precision@K
  - Recall@K
  - Normalized Discounted Cumulative Gain (nDCG@K)
  - Intra-List Diversity (ILD) via cosine distance
  - Long-tail Novelty

See DATA_ANALYST_RECOMMENDER_GUIDE.md Section 6.3 for theoretical definitions.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Optional


# ---------------------------------------------------------------------------
# Core Ranking Metrics
# ---------------------------------------------------------------------------

def precision_at_k(recommended: List[int], actual: List[int], k: int) -> float:
    """
    Compute Precision@K.

    Precision@K = |Rec@K ∩ Actual| / K

    Parameters
    ----------
    recommended : list of int
        Ordered list of recommended item (node) IDs.
    actual : list of int
        Ground truth items the user interacted with in the test set.
    k : int
        Cutoff rank.

    Returns
    -------
    float in [0, 1]
    """
    if k <= 0:
        return 0.0
    rec_k = set(recommended[:k])
    act_set = set(actual)
    if not act_set:
        return 0.0
    return len(rec_k & act_set) / k


def recall_at_k(recommended: List[int], actual: List[int], k: int) -> float:
    """
    Compute Recall@K.

    Recall@K = |Rec@K ∩ Actual| / |Actual|

    Parameters
    ----------
    recommended : list of int
        Ordered list of recommended item (node) IDs.
    actual : list of int
        Ground truth items the user interacted with in the test set.
    k : int
        Cutoff rank.

    Returns
    -------
    float in [0, 1]
    """
    if k <= 0:
        return 0.0
    rec_k = set(recommended[:k])
    act_set = set(actual)
    if not act_set:
        return 0.0
    return len(rec_k & act_set) / len(act_set)


def dcg_at_k(recommended: List[int], actual: List[int], k: int) -> float:
    """Compute DCG@K (Discounted Cumulative Gain)."""
    act_set = set(actual)
    dcg = 0.0
    for idx, item in enumerate(recommended[:k]):
        if item in act_set:
            dcg += 1.0 / np.log2(idx + 2)
    return dcg


def ndcg_at_k(recommended: List[int], actual: List[int], k: int) -> float:
    """
    Compute nDCG@K (Normalized Discounted Cumulative Gain).

    nDCG@K = DCG@K / IDCG@K

    Parameters
    ----------
    recommended : list of int
        Ordered list of recommended item (node) IDs.
    actual : list of int
        Ground truth items the user interacted with in the test set.
    k : int
        Cutoff rank.

    Returns
    -------
    float in [0, 1]
    """
    act_set = set(actual)
    if not act_set:
        return 0.0
    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(act_set), k)))
    if idcg == 0.0:
        return 0.0
    return dcg_at_k(recommended, actual, k) / idcg


# ---------------------------------------------------------------------------
# Diversity Metrics
# ---------------------------------------------------------------------------

def intra_list_diversity(slate: List[int], item_embeddings: Dict[int, np.ndarray]) -> float:
    """
    Compute Intra-List Diversity (ILD) for a recommendation slate.

    ILD = 1 - avg(cosine_similarity(i, j)) for all pairs (i, j) in slate.

    A lower cosine similarity average means a more diverse slate.

    Parameters
    ----------
    slate : list of int
        Recommended item IDs.
    item_embeddings : dict mapping item_id -> numpy array
        Dense embedding vectors for each item. Can be TF-IDF or learned embeddings.

    Returns
    -------
    float in [0, 1], where 1 = maximally diverse.
    """
    valid = [item_embeddings[i] for i in slate if i in item_embeddings]
    if len(valid) < 2:
        return 0.0

    vectors = np.array(valid)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1e-9, norms)
    normalized = vectors / norms

    sim_matrix = normalized @ normalized.T
    n = len(valid)
    # Mean of upper triangle (excluding diagonal)
    triu_indices = np.triu_indices(n, k=1)
    avg_sim = sim_matrix[triu_indices].mean()
    return 1.0 - float(avg_sim)


# ---------------------------------------------------------------------------
# Novelty / Serendipity Metrics
# ---------------------------------------------------------------------------

def long_tail_novelty(slate: List[int], item_popularity: Dict[int, float]) -> float:
    """
    Compute Long-tail Novelty for a recommendation slate.

    Novelty = mean(-log2(p(item))) over items in the slate.

    A higher novelty score means the model recommends less popular, long-tail items.

    Parameters
    ----------
    slate : list of int
        Recommended item IDs.
    item_popularity : dict mapping item_id -> float
        Probability p(item) = (interaction count of item) / (total interactions).

    Returns
    -------
    float >= 0
    """
    if not slate:
        return 0.0
    total = sum(
        -np.log2(item_popularity.get(item, 1e-9))
        for item in slate
    )
    return total / len(slate)


def build_popularity_distribution(df_interactions: pd.DataFrame) -> Dict[int, float]:
    """
    Build the item popularity distribution from interaction data.

    Parameters
    ----------
    df_interactions : pd.DataFrame
        Must contain column 'node_id'.

    Returns
    -------
    dict mapping node_id -> probability float
    """
    counts = df_interactions["node_id"].value_counts()
    total = counts.sum()
    return (counts / total).to_dict()


# ---------------------------------------------------------------------------
# Batch evaluation over all users
# ---------------------------------------------------------------------------

def evaluate_model(
    predictions: Dict[int, List[int]],
    ground_truth: Dict[int, List[int]],
    k: int = 5,
    item_embeddings: Optional[Dict[int, np.ndarray]] = None,
    item_popularity: Optional[Dict[int, float]] = None,
) -> pd.DataFrame:
    """
    Evaluate a recommendation model across all users.

    Parameters
    ----------
    predictions : dict mapping user_id -> ordered list of recommended node IDs
    ground_truth : dict mapping user_id -> list of actual node IDs in test set
    k : int
        Cutoff rank.
    item_embeddings : dict, optional
        Required to compute ILD.
    item_popularity : dict, optional
        Required to compute Novelty.

    Returns
    -------
    pd.DataFrame with columns:
        user_id, precision_at_k, recall_at_k, ndcg_at_k,
        ild (if embeddings provided), novelty (if popularity provided)
    """
    rows = []
    for user_id, rec in predictions.items():
        actual = ground_truth.get(user_id, [])
        row = {
            "user_id": user_id,
            f"precision@{k}": precision_at_k(rec, actual, k),
            f"recall@{k}": recall_at_k(rec, actual, k),
            f"ndcg@{k}": ndcg_at_k(rec, actual, k),
        }
        if item_embeddings is not None:
            row["ild"] = intra_list_diversity(rec[:k], item_embeddings)
        if item_popularity is not None:
            row["novelty"] = long_tail_novelty(rec[:k], item_popularity)
        rows.append(row)

    return pd.DataFrame(rows)


def summarize_evaluation(eval_df: pd.DataFrame) -> pd.DataFrame:
    """Return mean and std of each metric column across all users."""
    numeric_cols = eval_df.select_dtypes(include="number").drop(columns=["user_id"], errors="ignore")
    summary = pd.DataFrame({
        "mean": numeric_cols.mean(),
        "std": numeric_cols.std(),
        "median": numeric_cols.median(),
    })
    return summary
