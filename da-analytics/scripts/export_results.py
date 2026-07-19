"""
export_results.py
=================
Export recommendation slates from a trained model checkpoint to CSV files
ready for integration review or A/B testing.

Supports:
  - SRD (GRU4Rec + SRD Loss) checkpoint
  - BKT mastery scores

Usage:
    python scripts/export_results.py \\
        --model-checkpoint output/slates/srd_model.pt \\
        --output-dir output/slates \\
        --top-k 5
"""

import argparse
import os
import json
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from scripts.load_data import load_gold_table, build_user_item_matrix


def load_srd_checkpoint(checkpoint_path: str):
    """Load an SRD model checkpoint and return the model and item vocabulary."""
    from scripts.train_srd import GRU4RecBackbone
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    model = GRU4RecBackbone(vocab_size=ckpt["vocab_size"])
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt["item_vocab"]


def generate_srd_slates(model, item_vocab: dict, df_matrix: pd.DataFrame, top_k: int = 5) -> pd.DataFrame:
    """
    Generate recommendation slates for all users using a trained SRD model.

    For each user, use their historical affinity vector as a proxy context
    and score all items. Return the top-K items not already heavily interacted with.
    """
    reverse_vocab = {v: k for k, v in item_vocab.items()}
    pivot = build_user_item_matrix(df_matrix)
    rows = []

    with torch.no_grad():
        for user_id in pivot.index:
            # Build a short history sequence from the user's top interacted items
            user_row = pivot.loc[user_id]
            top_history = user_row.nlargest(10).index.tolist()
            seq = [item_vocab.get(i, 0) for i in top_history]
            seq_len = 10
            seq = ([0] * (seq_len - len(seq)) + seq)[-seq_len:]
            seq_tensor = torch.tensor([seq], dtype=torch.long)

            logits = model(seq_tensor).squeeze(0)  # [vocab_size]
            # Zero out already-seen items
            for item in top_history:
                idx = item_vocab.get(item, None)
                if idx is not None:
                    logits[idx] = float("-inf")

            top_indices = torch.topk(logits, k=top_k).indices.tolist()
            recommended = [reverse_vocab.get(i, i) for i in top_indices]

            for rank, node_id in enumerate(recommended, start=1):
                rows.append({
                    "user_id": user_id,
                    "rank": rank,
                    "recommended_node_id": node_id,
                    "model": "srd_gru4rec",
                })

    return pd.DataFrame(rows)


def main(checkpoint_path: str, output_dir: str, top_k: int):
    os.makedirs(output_dir, exist_ok=True)

    print("[Export] Loading Gold interaction matrix...")
    df_matrix = load_gold_table("gold_user_item_matrix")

    print("[Export] Loading SRD model checkpoint...")
    model, item_vocab = load_srd_checkpoint(checkpoint_path)

    print(f"[Export] Generating top-{top_k} slates for {len(df_matrix['user_id'].unique())} users...")
    df_slates = generate_srd_slates(model, item_vocab, df_matrix, top_k=top_k)

    output_path = os.path.join(output_dir, "srd_gru4rec_slates.csv")
    df_slates.to_csv(output_path, index=False)
    print(f"[Export] Slates written to: {output_path}")
    print(df_slates.head(10).to_string())

    # Summary stats
    print(f"\n[Export] Summary:")
    print(f"  Total users: {df_slates['user_id'].nunique()}")
    print(f"  Total slate entries: {len(df_slates)}")
    print(f"  Unique items recommended: {df_slates['recommended_node_id'].nunique()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export SRD model recommendation slates")
    parser.add_argument(
        "--model-checkpoint",
        default="output/slates/srd_model.pt",
        help="Path to the trained SRD model .pt checkpoint file",
    )
    parser.add_argument(
        "--output-dir",
        default="output/slates",
        help="Directory to write the output CSV file",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of items to recommend per user",
    )
    args = parser.parse_args()
    main(args.model_checkpoint, args.output_dir, args.top_k)
