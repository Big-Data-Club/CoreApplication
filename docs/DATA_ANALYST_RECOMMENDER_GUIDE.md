# Data Analyst Recommender Systems and CRS Integration Guide

| Field     | Value                     |
|-----------|---------------------------|
| Version   | 1.0.0                     |
| Status    | Approved                  |
| Date      | 2026-07-19                |
| Authors   | BDC Team                  |
| Reviewers | -                         |

## Revision History

| Version | Date       | Author   | Description   |
|---------|------------|----------|---------------|
| 1.0.0   | 2026-07-19 | BDC Team | Initial draft |

---

## 1. Overview

This document provides a technical guide for Data Analysts (DA) and Machine Learning (ML) engineers working on the personalization and recommendation components of the Big Data Club (BDC) Learning Management System (LMS). 

It details the theoretical foundations of Recommender Systems (RS) and Conversational Recommender Systems (CRS) implemented within the BDC platform. It also provides instructions on accessing data from the Medallion Lakehouse inside [personalize-service](file:///home/phucnhan/codespace/bdc/CoreApplication/personalize-service) and establishing offline benchmarks against heuristic baselines.

---

## 2. Theoretical Framework of Recommender Systems (RS)

Recommender Systems are modeled mathematically to predict student affinity towards knowledge concepts (items). DAs are expected to develop algorithms across four primary paradigms:

### 2.1 Collaborative Filtering (CF)
Collaborative Filtering assumes that users who agreed in the past will agree in the future. In an LMS context, student behavior is represented using an implicit feedback matrix, where interactions (views, quiz attempts, correct answers) map to numerical affinity scores.

*   **Matrix Factorization (MF):** Decomposes the user-item interaction matrix $R \in \mathbb{R}^{M \times N}$ into low-rank matrices $P \in \mathbb{R}^{M \times K}$ and $Q \in \mathbb{R}^{N \times K}$ representing user and item latent features, such that:
    $$\hat{R} \approx P Q^T$$
*   **Neural Collaborative Filtering (NCF):** Replaces the inner product of MF with a neural network architecture capable of learning non-linear relationships between users and items.

### 2.2 Content-Based Filtering (CBF)
Content-Based Filtering recommends items similar to those the student liked or engaged with in the past. 
*   **Feature Vectors:** Formed using TF-IDF (Term Frequency-Inverse Document Frequency) or dense embeddings of lesson bodies and titles.
*   **Cosine Similarity:** Measures the angle between the student's historical interest vector $u$ and a candidate item vector $v$:
    $$\text{Similarity}(u, v) = \frac{u \cdot v}{\|u\| \|v\|}$$

### 2.3 Knowledge Graph-Based Recommendation (KGR)
The learning syllabus is structured as a directed Knowledge Graph (KG) where concepts have topological relations such as `prerequisite` and `extends`.
*   **Path-Based Recommendation:** Recommends concepts based on structural dependencies. A student cannot be recommended concept $B$ unless they have achieved a mastery threshold in its prerequisite concept $A$.
*   **Graph Neural Networks (GNN):** Algorithms such as LightGCN propagate node embeddings over the student-concept bipartite graph and the concept-concept prerequisite graph to predict the next best learning action.

### 2.4 Sequential Recommendation (SR)
Models student learning as a sequence of historical interactions. Given a history $S = \{i_1, i_2, \dots, i_t\}$, the model predicts the probability of the next interaction $i_{t+1}$:
$$P(i_{t+1} \mid i_1, i_2, \dots, i_t)$$
DAs can implement Markov Chains, Recurrent Neural Networks (RNNs) (e.g., GRU4Rec), or Transformer-based models (e.g., SASRec) to capture temporal dependencies and forgetting curves.

---

## 3. Theoretical Framework of Conversational Recommender Systems (CRS)

Unlike static recommenders, a Conversational Recommender System (CRS) establishes a multi-turn dialogue feedback loop with the student. It utilizes natural language to elicit preferences, resolve ambiguities, deliver recommendations, explain suggestions, and process critiques.

### 3.1 The CRS Lifecycle

```
     +--------------------------+
     | Preference Elicitation   | <---------------+
     +-------------+------------+                 |
                   |                              | Refine preferences
                   v                              | or apply critique
     +--------------------------+                 |
     | Generate Recommendation  +-----------------+
     +-------------+------------+
                   |
                   v
     +--------------------------+
     |   Provide Explanation    |
     +-------------+------------+
                   |
                   v
     +--------------------------+
     |     Collect Feedback     | (Acceptance / Rejection / Critique)
     +--------------------------+
```

### 3.2 Remodeled User Intents for CRS
To support this loop, the intent classification layer in [intent_weight_model.py](file:///home/phucnhan/codespace/bdc/CoreApplication/ai-service/app/agents/core/intent_weight_model.py) and [planner.py](file:///home/phucnhan/codespace/bdc/CoreApplication/ai-service/app/agents/core/planner.py) has been modeled into four distinct CRS dialogue actions:

1.  **Elicitation (`elicitation`):** The student explicitly shares details about their learning style, speed preferences, or topics of interest (e.g., "I prefer practical exercises over reading theory", "I want to study Advanced Python").
2.  **Recommendation Request (`recommendation`):** The student directly asks the system for guidance or next study steps (e.g., "What should I study next?", "Nên học gì tiếp theo?").
3.  **Feedback and Critique (`feedback`):** The student accepts, rejects, or critiques a suggestion (e.g., "This topic is too hard, show me something easier", "I do not want to learn SQL today").
4.  **Explanation Request (`explanation_request`):** The student asks why a specific concept or course path was recommended (e.g., "Why do I need to study this concept?", "Tại sao lại gợi ý bài này?").

---

## 4. System Architecture and Medallion Lakehouse Integration

The recommendation engine leverages a Medallion Lakehouse pattern running inside `personalize-service`. 

### 4.1 Data Flow Sequence

```
Student UI           LMS Service          Kafka Broker        Personalize Service
    |                     |                    |                       |
    |-- Interaction ----->|                    |                       |
    |   (click/quiz/AI)   |-- Publish Event -->|                       |
    |                     |   (interactions)   |-- Consume Message --->|
    |                     |                    |                       |-- Ingest to Bronze
    |                     |                    |                       |-- Compute Gold Matrix
    |                     |                    |                       |-- Export to Parquet
```

### 4.2 Lakehouse Schema Directory
The database file is located at `/app/data/student_analytics.duckdb` within the `personalize-service` container, which maps to the persistent host volume.

#### Bronze Layer (Raw Event Logs)
The table `bronze_interactions` stores raw interaction events consumed from the Kafka topic `lms.analytics.interactions`. Columns include:
*   `interaction_id` (BIGINT): Unique identifier.
*   `user_id` (BIGINT): Student identifier.
*   `course_id` (BIGINT): Course identifier.
*   `node_id` (BIGINT): Knowledge node identifier.
*   `action_type` (VARCHAR): Interaction type (e.g., `lesson_view`, `quick_check_correct`, `ask_ai`).
*   `score` (DOUBLE): Optional performance score.
*   `created_at` (TIMESTAMP): Event timestamp.

*Note: Events older than 7 days are moved to partitioned Parquet files under `/app/data/lakehouse/bronze/interactions/` and deleted from the DuckDB table. DAs should query the Silver view `unified_interactions` to retrieve the entire historical dataset.*

#### Gold Layer (Analytical Views for Modeling)
1.  **`gold_user_item_matrix`:** Computes the implicit affinity score weights for user-concept pairs:
    *   `lesson_view` / `lesson_viewed`: 1.0
    *   `lesson_complete` / `lesson_completed`: 2.0
    *   `flashcard_flip`: 1.0
    *   `quick_check_correct`: 2.0
    *   `quick_check_incorrect`: 0.5
    *   `ask_ai`: 1.5
2.  **`gold_concept_struggles`:** Groups students struggling with specific concepts (defined as $\ge 2$ incorrect quick checks and incorrect counts exceeding correct counts).
3.  **`gold_study_recommendations`:** Executes the baseline heuristic next-best-action rule.

---

## 5. Data Access for Data Analysts

### 5.1 Shared Volume Access
To train models offline, DAs can access the raw exported Parquet files directly from the host filesystem. The export directory maps to:
`./data/lakehouse/gold/`

To force a refresh of the Parquet exports, trigger the export endpoint:
```bash
curl -X POST -H "X-AI-Secret: <AI_SERVICE_SECRET>" http://localhost:8085/personalize/analytics/gold/export
```

### 5.2 REST API Endpoints
Endpoints require the `X-AI-Secret` header for internal authentication.

*   **Implicit Affinity Matrix:** `GET /personalize/analytics/gold/interaction-matrix`
*   **Struggling Concepts:** `GET /personalize/analytics/gold/concept-struggles`
*   **Overall Student Metrics:** `GET /personalize/analytics/gold/student-metrics`
*   **Daily User Logins & DAU:** `GET /personalize/analytics/gold/daily-logins`
*   **Course Discovery Recommendations:** `GET /personalize/analytics/gold/discovery-recommendations`

---

## 6. Python Code Guide for Data Analysts

This section provides Python code templates for DAs to load the Lakehouse data, run the heuristic baseline, train a recommender model, and calculate offline metrics.

### 6.1 Loading Data from DuckDB and Parquet
```python
import os
import pandas as pd
import duckdb

# Method A: Direct Parquet loading
gold_dir = "./data/lakehouse/gold"
df_matrix = pd.read_parquet(os.path.join(gold_dir, "gold_user_item_matrix.parquet"))

# Method B: Direct connection to DuckDB file
db_path = "./data/student_analytics.duckdb"
conn = duckdb.connect(db_path)

# Query unified historical interactions
df_history = conn.execute("SELECT * FROM unified_interactions").df()
print(df_history.head())
```

### 6.2 Collaborative Filtering Baseline Model
The following template uses Cosine Similarity over user vectors to compute collaborative recommendations.
```python
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

def train_collaborative_recommender(df_matrix):
    # Pivot dataframe to construct User-Item interaction matrix
    pivot_df = df_matrix.pivot(index='user_id', columns='node_id', values='implicit_affinity_score').fillna(0)
    
    # Compute Cosine Similarity between users
    user_sim = cosine_similarity(pivot_df)
    user_sim_df = pd.DataFrame(user_sim, index=pivot_df.index, columns=pivot_df.index)
    
    return pivot_df, user_sim_df

def recommend_items(user_id, pivot_df, user_sim_df, top_n=5):
    if user_id not in pivot_df.index:
        return []
    
    # Get similar users
    similar_users = user_sim_df[user_id].sort_values(ascending=False).index[1:11]
    
    # Aggregate weights of items rated by similar users
    user_ratings = pivot_df.loc[user_id]
    unrated_items = user_ratings[user_ratings == 0].index
    
    scores = {}
    for item in unrated_items:
        weighted_score = 0
        sim_sum = 0
        for sim_user in similar_users:
            rating = pivot_df.loc[sim_user, item]
            similarity = user_sim_df.loc[user_id, sim_user]
            if rating > 0:
                weighted_score += rating * similarity
                sim_sum += similarity
        scores[item] = (weighted_score / sim_sum) if sim_sum > 0 else 0
        
    recommended_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [item_id for item_id, score in recommended_items]
```

### 6.3 Computing Offline Metrics (Evaluation Framework)
DAs must evaluate new models against the heuristic baseline using a Train/Test split. The metric equations are defined as:

*   **Precision@K:** Proportion of recommended items that are relevant to the user.
    $$\text{Precision@K} = \frac{|\text{Recommended Items @ K} \cap \text{Test Items}|}{K}$$
*   **Recall@K:** Proportion of relevant items that are successfully recommended.
    $$\text{Recall@K} = \frac{|\text{Recommended Items @ K} \cap \text{Test Items}|}{|\text{Test Items}|}$$
*   **Normalized Discounted Cumulative Gain (nDCG@K):** Evaluates the ranking quality of recommendations.
    $$\text{DCG@K} = \sum_{i=1}^{K} \frac{2^{rel_i} - 1}{\log_2(i + 1)}, \quad \text{nDCG@K} = \frac{\text{DCG@K}}{\text{IDCG@K}}$$

```python
def calculate_precision_recall_at_k(recommended, actual, k):
    rec_k = set(recommended[:k])
    act_set = set(actual)
    if not act_set:
        return 0.0, 0.0
    
    intersection = len(rec_k.intersection(act_set))
    precision = intersection / k
    recall = intersection / len(act_set)
    return precision, recall

def calculate_ndcg_at_k(recommended, actual, k):
    rec_k = recommended[:k]
    act_set = set(actual)
    
    dcg = 0.0
    for idx, item in enumerate(rec_k):
        if item in act_set:
            dcg += 1.0 / np.log2(idx + 2)
            
    idcg = sum(1.0 / np.log2(i + 2) for i in range(min(len(act_set), k)))
    if idcg == 0.0:
        return 0.0
    return dcg / idcg

# Example usage for evaluation
actual_interactions = [102, 105, 108]
heuristic_recommendations = [102, 104, 109, 110, 115]
ml_recommendations = [102, 105, 111, 112, 115]

p_h, r_h = calculate_precision_recall_at_k(heuristic_recommendations, actual_interactions, k=5)
ndcg_h = calculate_ndcg_at_k(heuristic_recommendations, actual_interactions, k=5)

p_ml, r_ml = calculate_precision_recall_at_k(ml_recommendations, actual_interactions, k=5)
ndcg_ml = calculate_ndcg_at_k(ml_recommendations, actual_interactions, k=5)

print(f"Heuristic Baseline - Precision@5: {p_h:.2f}, Recall@5: {r_h:.2f}, nDCG@5: {ndcg_h:.2f}")
print(f"ML Model Recommender - Precision@5: {p_ml:.2f}, Recall@5: {r_ml:.2f}, nDCG@5: {ndcg_ml:.2f}")
```

---

## 7. A/B Testing and Online Deployments

Once an ML model demonstrates superior offline metrics compared to the heuristic baseline, it can be integrated online. DAs can deploy models using two integration patterns:

### 7.1 Batch Score Push Model
Ideal for matrix factorization or GNN-based models that do not require real-time updates.
1.  A cron job executes daily to train the model and generate recommendations.
2.  The script writes the computed user-item recommendations directly to a table (e.g., `ml_recommendations`) in `postgres-lms`.
3.  The LMS frontend and AI Service fetch recommendations directly from this table.

### 7.2 Real-Time API Pull Model
Ideal for deep learning models or sequential models utilizing real-time sessions.
1.  The model is wrapped in a Python microservice exposing a REST API endpoint.
2.  The endpoint receives the student ID, queries active metrics from the DuckDB Lakehouse, and performs real-time inference.
3.  The LMS or AI Planner queries this endpoint synchronously.
4.  User interaction clicks (`recommendation_accept` or `recommendation_reject`) are tracked via Kafka to dynamically adjust A/B split distributions.

---

## 8. Step-by-Step Workflow for Data Analysts

This section outlines the step-by-step workflow for extracting data, implementing the training-time objectives (SRD and DivKG), generating recommendation outputs, and executing offline comparisons.

### Step 1: Data Extraction
The DA must extract historical interactions from the Lakehouse and structural relationships from the Knowledge Graph (KG).

1.  **Extract Interactions:** Trigger a Parquet export on the server and load the unified interactions:
    ```python
    import pandas as pd
    import duckdb

    # Connect to DuckDB database file
    conn = duckdb.connect("./data/student_analytics.duckdb")
    df_interactions = conn.execute("SELECT * FROM unified_interactions").df()
    ```
2.  **Extract Knowledge Graph:** Query the PostgreSQL database or Neo4j instance to retrieve concept relations:
    ```python
    # Example database query to fetch prerequisite links
    df_kg = conn.execute("SELECT * FROM gold_concept_struggles").df()
    # Alternatively, fetch relations from Neo4j (prerequisite, extends)
    ```

### Step 2: Supervised Pre-Training with Soft-Rank Diversity (SRD) Loss
During the supervised pre-training phase, the DA trains a backbone model (e.g., GRU4Rec or a Graph Neural Network) to predict the next concept interaction. Rather than using standard cross-entropy loss, the DA integrates the SRD loss to penalize recommending highly similar items.

```python
import torch
import torch.nn as nn
import torch.nn.functional as F

class SRDLoss(nn.Module):
    def __init__(self, temperature=1.0, w_div=0.1):
        super(SRDLoss, self).__init__()
        self.temperature = temperature
        self.w_div = w_div  # Diversity loss weight modifier

    def forward(self, logits, item_embeddings, targets):
        # logits: [batch_size, num_candidates]
        # item_embeddings: [num_candidates, embedding_dim]
        # targets: [batch_size]

        # 1. Compute standard cross-entropy loss (accuracy objective)
        loss_ce = F.cross_entropy(logits, targets)

        # 2. Soft-select candidates using temperature-scaled softmax
        soft_selection = F.softmax(logits / self.temperature, dim=-1)  # [batch_size, num_candidates]

        # 3. Compute cosine similarity matrix S of candidate item embeddings
        norm_embeddings = F.normalize(item_embeddings, p=2, dim=-1)
        S = torch.matmul(norm_embeddings, norm_embeddings.t())  # [num_candidates, num_candidates]

        # 4. Compute weight-quadratic over the similarity matrix S (diversity objective)
        # Factorization approach: H_t_w = S * soft_selection^T
        # Cost is reduced to O(d * M) by computing matrix vector multiplication
        weighted_similarity = torch.matmul(soft_selection, S)  # [batch_size, num_candidates]
        div_loss = torch.sum(weighted_similarity * soft_selection, dim=-1).mean()

        # 5. Composite loss
        total_loss = loss_ce + self.w_div * div_loss
        return total_loss
```

### Step 3: Fine-Tuning with Reinforcement Learning (DivKG)
After supervised pre-training is complete, the DA freezes the reference policy model ($\pi_{\text{ref}}$) and fine-tunes the trainable policy model ($\pi_\theta$) using the REINFORCE algorithm with RLOO (Reinforce Leave-One-Out) baseline.

```python
import numpy as np

def compute_rewards(sampled_slate, actual_interactions, item_popularity):
    # sampled_slate: list of concept IDs recommended by the model (size K_s=50)
    # actual_interactions: list of concept IDs the student interacted with
    # item_popularity: dict of concept interaction frequencies (for novelty calculation)

    # 1. NDCG Reward (Accuracy)
    ndcg = calculate_ndcg_at_k(sampled_slate, actual_interactions, k=50)

    # 2. Novelty Reward (Long-tail boost)
    # Measured as self-information: -log2(p(item))
    novelty = 0.0
    for item in sampled_slate:
        prob = item_popularity.get(item, 1e-5)
        novelty += -np.log2(prob)
    novelty /= len(sampled_slate)

    # 3. Composite Reward
    reward = ndcg + 0.2 * novelty
    return reward

def train_rl_step(policy_model, ref_model, optimizer, state, actual_interactions, item_popularity, kl_coef=0.1):
    optimizer.zero_grad()

    # 1. Sample slate from trainable policy model
    logits_theta = policy_model(state)
    probs_theta = F.softmax(logits_theta, dim=-1)
    # Sample a slate of Ks=50 items
    sampled_slate = torch.multinomial(probs_theta, num_samples=50, replacement=False)[0].tolist()

    # 2. Compute logits from frozen reference model
    with torch.no_grad():
        logits_ref = ref_model(state)
        probs_ref = F.softmax(logits_ref, dim=-1)

    # 3. Calculate Reward
    raw_reward = compute_rewards(sampled_slate, actual_interactions, item_popularity)

    # 4. Calculate KL divergence penalty to anchor the policy
    kl_div = F.kl_div(probs_theta.log(), probs_ref, reduction='sum')

    # 5. Compute policy gradient loss
    # Simple REINFORCE implementation
    log_prob_slate = 0.0
    for item in sampled_slate:
        log_prob_slate += probs_theta[item].log()

    loss = -log_prob_slate * (raw_reward - kl_coef * kl_div)
    loss.backward()
    optimizer.step()
    
    return loss.item(), raw_reward
```

### Step 4: Generating Output Slates
The output of the trained model must be saved as a mapping table in the database or exposed via an API payload.
*   **API Output Schema:**
    ```json
    {
      "user_id": 42,
      "course_id": 3,
      "recommended_slate": [
        {
          "node_id": 105,
          "node_name": "Array Operations",
          "score": 0.92,
          "reason": "prerequisite_of_sorting"
        },
        {
          "node_id": 112,
          "node_name": "Bubble Sort",
          "score": 0.81,
          "reason": "struggling_concept_retry"
        }
      ]
    }
    ```

### Step 5: Offline Evaluation & Comparison
The DA must generate a comparison table evaluating the new models against the heuristic baseline.

| Algorithm Model | Precision@5 | Recall@5 | nDCG@5 | Intra-List Diversity (Cosine) | Long-tail Novelty |
|---|---|---|---|---|---|
| **Heuristic Baseline** | 0.40 | 0.25 | 0.38 | 0.72 | 1.20 |
| **SRD Model (Method 1)** | 0.42 | 0.28 | 0.41 | 0.48 | 1.85 |
| **DivKG Model (Method 2)** | 0.45 | 0.31 | 0.44 | 0.35 | 2.10 |

*Note: Lower Intra-List Diversity Cosine Score indicates a more diverse recommendation list.*

