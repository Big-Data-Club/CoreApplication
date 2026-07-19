"""
train_srd.py
============
Supervised pre-training with Soft-Rank Diversity (SRD) Loss.

METHOD 1 of the two-stage training approach described in
DATA_ANALYST_RECOMMENDER_GUIDE.md, Section 8, Step 2.

SRD penalizes the recommender model for selecting highly similar items by adding
a differentiable intra-list diversity objective on top of standard cross-entropy loss.

Training requires:
  - A backbone sequence model (GRU in this example) that outputs logits over items.
  - Pre-trained or learned item embeddings.

Usage:
    python scripts/train_srd.py --epochs 20 --output output/slates/srd_model.pt
"""

import argparse
import os
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from scripts.load_data import load_gold_table, build_user_item_matrix, train_test_split_temporal


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

class InteractionSequenceDataset(Dataset):
    """
    Converts user interaction sequences into (input_sequence, next_item) training pairs.
    Each sample is a sliding window over a user's interaction history.
    """

    def __init__(self, df: pd.DataFrame, seq_len: int = 10, item_vocab: dict | None = None):
        self.seq_len = seq_len
        self.samples = []

        if item_vocab is None:
            all_items = df["node_id"].unique()
            self.item_vocab = {item: idx for idx, item in enumerate(sorted(all_items))}
        else:
            self.item_vocab = item_vocab

        self.vocab_size = len(self.item_vocab)

        for user_id, group in df.groupby("user_id"):
            items = group.sort_values("created_at")["node_id"].tolist()
            items_encoded = [self.item_vocab.get(i, 0) for i in items]
            for i in range(len(items_encoded) - 1):
                start = max(0, i - seq_len + 1)
                seq = items_encoded[start:i + 1]
                # Pad to fixed length
                padded = [0] * (seq_len - len(seq)) + seq
                target = items_encoded[i + 1]
                self.samples.append((padded, target))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        seq, target = self.samples[idx]
        return torch.tensor(seq, dtype=torch.long), torch.tensor(target, dtype=torch.long)


# ---------------------------------------------------------------------------
# Backbone model
# ---------------------------------------------------------------------------

class GRU4RecBackbone(nn.Module):
    """
    Simple GRU-based sequential recommendation backbone.
    Outputs a logit vector over all items in the vocabulary.
    """

    def __init__(self, vocab_size: int, embed_dim: int = 64, hidden_dim: int = 128):
        super().__init__()
        self.embedding = nn.Embedding(vocab_size + 1, embed_dim, padding_idx=0)
        self.gru = nn.GRU(embed_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)

    def forward(self, x):
        # x: [batch, seq_len]
        emb = self.embedding(x)           # [batch, seq_len, embed_dim]
        out, _ = self.gru(emb)            # [batch, seq_len, hidden_dim]
        last = out[:, -1, :]              # [batch, hidden_dim]
        logits = self.fc(last)            # [batch, vocab_size]
        return logits

    def item_embeddings(self):
        """Return item embedding weight matrix: [vocab_size, embed_dim]."""
        return self.embedding.weight[1:]  # Exclude padding index 0


# ---------------------------------------------------------------------------
# SRD Loss
# ---------------------------------------------------------------------------

class SRDLoss(nn.Module):
    """
    Soft-Rank Diversity Loss.

    Combines standard cross-entropy loss with a pairwise diversity penalty
    computed using a temperature-scaled softmax and cosine similarity.

    Parameters
    ----------
    temperature : float
        Controls the sharpness of the soft selection distribution.
    w_div : float
        Weight of the diversity penalty term relative to the accuracy loss.
    """

    def __init__(self, temperature: float = 1.0, w_div: float = 0.1):
        super().__init__()
        self.temperature = temperature
        self.w_div = w_div

    def forward(self, logits: torch.Tensor, item_embeds: torch.Tensor, targets: torch.Tensor):
        # 1. Standard cross-entropy accuracy objective
        loss_ce = F.cross_entropy(logits, targets)

        # 2. Soft candidate selection
        soft_sel = F.softmax(logits / self.temperature, dim=-1)  # [B, V]

        # 3. Cosine similarity matrix over item embeddings
        norm_embeds = F.normalize(item_embeds, p=2, dim=-1)       # [V, D]
        S = torch.matmul(norm_embeds, norm_embeds.t())             # [V, V]

        # 4. Weight-quadratic diversity penalty (O(D*V) factorized)
        weighted_sim = torch.matmul(soft_sel, S)                   # [B, V]
        div_loss = (weighted_sim * soft_sel).sum(dim=-1).mean()

        return loss_ce + self.w_div * div_loss


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train(
    model: GRU4RecBackbone,
    dataloader: DataLoader,
    optimizer: torch.optim.Optimizer,
    criterion: SRDLoss,
    device: torch.device,
    epoch: int,
) -> float:
    model.train()
    total_loss = 0.0
    for batch_idx, (sequences, targets) in enumerate(dataloader):
        sequences, targets = sequences.to(device), targets.to(device)
        optimizer.zero_grad()
        logits = model(sequences)
        item_embeds = model.item_embeddings()
        loss = criterion(logits, item_embeds, targets)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item()

    avg_loss = total_loss / len(dataloader)
    print(f"[SRD] Epoch {epoch:3d} | Loss: {avg_loss:.4f}")
    return avg_loss


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(epochs: int, output_path: str, w_div: float, temperature: float, batch_size: int):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[SRD] Using device: {device}")

    print("[SRD] Loading data...")
    try:
        from scripts.load_data import load_duckdb_view
        df = load_duckdb_view(
            "SELECT user_id, node_id, created_at FROM unified_interactions ORDER BY created_at ASC"
        )
    except Exception:
        print("[SRD] Falling back to Parquet gold_user_item_matrix...")
        df = load_gold_table("gold_user_item_matrix")[["user_id", "node_id"]].copy()
        df["created_at"] = pd.Timestamp.now()

    train_df, _ = train_test_split_temporal(df, test_frac=0.1)
    dataset = InteractionSequenceDataset(train_df, seq_len=10)
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    vocab_size = dataset.vocab_size
    print(f"[SRD] Vocabulary size: {vocab_size} | Train samples: {len(dataset)}")

    model = GRU4RecBackbone(vocab_size=vocab_size).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    criterion = SRDLoss(temperature=temperature, w_div=w_div)

    for epoch in range(1, epochs + 1):
        train(model, dataloader, optimizer, criterion, device, epoch)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    torch.save({
        "state_dict": model.state_dict(),
        "item_vocab": dataset.item_vocab,
        "vocab_size": vocab_size,
        "hyperparams": {"temperature": temperature, "w_div": w_div},
    }, output_path)
    print(f"[SRD] Model checkpoint saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train GRU4Rec backbone with SRD Loss")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--output", default="output/slates/srd_model.pt")
    parser.add_argument("--w-div", type=float, default=0.1, help="Diversity loss weight")
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--batch-size", type=int, default=64)
    args = parser.parse_args()
    main(args.epochs, args.output, args.w_div, args.temperature, args.batch_size)
