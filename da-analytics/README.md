# BDC Data Analytics Workspace

| Field     | Value                                                              |
|-----------|--------------------------------------------------------------------|
| Version   | 1.0.0                                                              |
| Status    | Active                                                             |
| Date      | 2026-07-19                                                         |
| Authors   | BDC Data Team                                                      |
| Parent Repo | [Big-Data-Club/CoreApplication](https://github.com/Big-Data-Club/CoreApplication) |

This repository is a **Git submodule** of the BDC CoreApplication. It provides the complete offline analytics and machine learning workspace for Data Analysts (DA) and ML Engineers working on the BDC personalization and recommender system.

---

## Purpose

The BDC platform collects micro-interaction data (lesson views, quiz attempts, AI queries, flashcard flips) from students and stores them in a Medallion Lakehouse (Bronze, Silver, Gold layers) powered by DuckDB and Parquet files inside `personalize-service`.

This workspace enables DAs to:

1. Load and explore that Lakehouse data locally.
2. Reproduce and extend the heuristic recommendation baseline.
3. Train and evaluate advanced ML models (Collaborative Filtering, Knowledge Graph, Sequential, Deep Knowledge Tracing).
4. Compare model outputs against the baseline using standardized offline metrics.
5. Export trained model outputs for integration back into the platform.

---

## Directory Structure

```
da-analytics/
|
|-- notebooks/                  Exploratory and training Jupyter notebooks
|   |-- 01_data_exploration.ipynb       Load and profile Lakehouse tables
|   |-- 02_heuristic_baseline.ipynb     Reproduce the gold_study_recommendations view
|   |-- 03_collaborative_filtering.ipynb Cosine CF + Matrix Factorization (ALS)
|   |-- 04_knowledge_tracing.ipynb      BKT and DKT cognitive modeling
|   |-- 05_behavioral_friction.ipynb    LSTM friction / stuck detection
|   |-- 06_srd_loss_training.ipynb      Soft-Rank Diversity pre-training
|   |-- 07_divkg_rl_finetuning.ipynb   DivKG REINFORCE fine-tuning
|   `-- 08_offline_evaluation.ipynb     Unified metric comparison table
|
|-- scripts/                    Production-ready Python scripts
|   |-- load_data.py            Utility to read Parquet / DuckDB into pandas
|   |-- metrics.py              Precision@K, Recall@K, nDCG@K, ILD, Novelty
|   |-- train_bkt.py            Bayesian Knowledge Tracing training (pyBKT)
|   |-- train_cf.py             Collaborative Filtering (ALS / NCF)
|   |-- train_srd.py            SRD loss supervised pre-training (PyTorch)
|   |-- train_divkg.py          DivKG REINFORCE fine-tuning (PyTorch)
|   `-- export_results.py       Write recommendation slates to output/
|
|-- data/                       Data directory (not committed to git)
|   |-- lakehouse/              Symlink or copy from personalize-service shared volume
|   |   |-- gold/               Gold Parquet exports
|   |   `-- bronze/             Bronze historical Parquet partitions
|   `-- external/               Any supplementary external datasets
|
|-- output/                     Model outputs and evaluation reports
|   |-- slates/                 Recommendation slate CSVs per model
|   `-- evaluation/             Metric comparison tables (CSV / HTML)
|
|-- requirements.txt            Python dependencies
|-- .gitignore                  Ignores data/, __pycache__, .ipynb_checkpoints
`-- README.md                   This file
```

---

## Quick Start

### 1. Prerequisites

- Python 3.10 or higher
- Access to the BDC development server or the `personalize-service` shared volume
- The `X-AI-Secret` environment variable for API access

### 2. Install Dependencies

```bash
cd da-analytics
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Obtain Data

**Option A: Direct Parquet access (recommended for offline training)**

If you have access to the host filesystem where `personalize-service` is running:

```bash
# Create symlink to the shared volume
ln -s /path/to/personalize-service/data/lakehouse ./data/lakehouse
```

**Option B: Trigger a fresh export via the Dashboard or API**

Log in to the Lakehouse Control Center and press **Export Server Parquet**, or run:

```bash
export AI_SECRET="<your-x-ai-secret>"
curl -X POST \
  -H "X-AI-Secret: ${AI_SECRET}" \
  http://localhost:8085/personalize/analytics/gold/export
```

This generates five Parquet files in the shared volume:

| File | Description |
|------|-------------|
| `gold_student_course_metrics.parquet` | Per-student engagement and accuracy metrics |
| `gold_concept_struggles.parquet` | Concepts where students consistently fail |
| `gold_user_item_matrix.parquet` | Implicit affinity scores per user-concept pair |
| `gold_struggle_alerts.parquet` | Triggered proactive learning alerts |
| `gold_study_recommendations.parquet` | Heuristic next-best-action recommendations |

**Option C: REST API (for smaller data pulls)**

See [Section 5 of the Recommender Guide](https://github.com/Big-Data-Club/CoreApplication/blob/main/docs/DATA_ANALYST_RECOMMENDER_GUIDE.md#5-data-access-for-data-analysts).

### 4. Run Notebooks in Order

Start Jupyter Lab and open the notebooks sequentially:

```bash
jupyter lab
```

| Order | Notebook | Goal |
|-------|----------|------|
| 1 | `01_data_exploration.ipynb` | Understand data distribution, null rates, interaction volume |
| 2 | `02_heuristic_baseline.ipynb` | Replicate the SQL heuristic baseline in Python, record baseline scores |
| 3 | `03_collaborative_filtering.ipynb` | Train CF model and compare with baseline |
| 4 | `04_knowledge_tracing.ipynb` | Model cognitive mastery per student-concept pair |
| 5 | `05_behavioral_friction.ipynb` | Train the LSTM stuck-detection classifier |
| 6 | `06_srd_loss_training.ipynb` | Pre-train with Soft-Rank Diversity loss |
| 7 | `07_divkg_rl_finetuning.ipynb` | Fine-tune policy with REINFORCE + KL penalty |
| 8 | `08_offline_evaluation.ipynb` | Generate the final metric comparison table |

---

## Key Documentation References

The following documents in the parent CoreApplication repository provide essential context. Always read these before starting work.

| Document | Description |
|----------|-------------|
| [DATA_ANALYST_RECOMMENDER_GUIDE.md](https://github.com/Big-Data-Club/CoreApplication/blob/main/docs/DATA_ANALYST_RECOMMENDER_GUIDE.md) | Primary guide: theory, schema, step-by-step workflow, code templates for SRD and DivKG |
| [LAKEHOUSE_PERSONALIZATION.md](https://github.com/Big-Data-Club/CoreApplication/blob/main/docs/LAKEHOUSE_PERSONALIZATION.md) | Medallion Lakehouse architecture, DuckDB schema, Parquet partitioning, data flow |
| [kafka-events.md](https://github.com/Big-Data-Club/CoreApplication/blob/main/docs/kafka-events.md) | All Kafka event schemas including `lms.analytics.interactions` interaction event payload |
| [TECHNICAL_NOTES.md](https://github.com/Big-Data-Club/CoreApplication/blob/main/docs/TECHNICAL_NOTES.md) | Engineering decisions, service boundaries, and API contracts |

---

## Modeling Roadmap

The modeling work is organized in two phases:

### Phase 1: Heuristic Baseline (Complete)

The production system currently uses a deterministic SQL-based heuristic view (`gold_study_recommendations`) running inside DuckDB. This is the benchmark every ML model must outperform.

**Baseline logic:**

- If the student has a `node_id` with a high `struggle_rate` in `gold_concept_struggles`, recommend `review_struggle_concept`.
- Else if the student's overall `check_accuracy` is below 60%, recommend `discuss_with_ai`.
- Otherwise recommend `learn_next_lesson`.

### Phase 2: Cognitive and Behavioral Modeling (In Progress)

DAs are expected to build and evaluate the following models:

| Model | Library | Replaces |
|-------|---------|----------|
| Bayesian Knowledge Tracing (BKT) | `pyBKT` | Hardcoded struggle thresholds |
| Deep Knowledge Tracing (DKT) | `PyTorch` | BKT where sequences are long |
| Collaborative Filtering (ALS / NCF) | `implicit`, `PyTorch` | Heuristic affinity scores |
| Sequential Recommender (GRU4Rec / SASRec) | `PyTorch` | Static next-lesson rules |
| LSTM Friction Classifier | `PyTorch` | Hardcoded stuck-detection rules |
| SRD + DivKG | `PyTorch` | Diversity-unaware baselines |

---

## Evaluation Protocol

All models must be evaluated on a held-out test split using the following metrics. Results must be submitted to `output/evaluation/` as a CSV file.

| Metric | Symbol | Formula |
|--------|--------|---------|
| Precision at K | P@K | `|Rec@K ∩ Test| / K` |
| Recall at K | R@K | `|Rec@K ∩ Test| / |Test|` |
| Normalized DCG at K | nDCG@K | `DCG@K / IDCG@K` |
| Intra-List Diversity | ILD | `1 - avg cosine similarity within slate` |
| Long-tail Novelty | Nov | `avg(-log2(p(item)))` across slate |

See `scripts/metrics.py` for the reference implementation and `notebooks/08_offline_evaluation.ipynb` for the comparison template.

---

## Submitting Results

After completing training and evaluation:

1. Export your recommendation slate to `output/slates/<model_name>_slates.csv`.
2. Export the evaluation table to `output/evaluation/<model_name>_metrics.csv`.
3. Open a Pull Request against this repository with your notebooks and scripts.
4. Tag your PR with the label `da-model-submission` for review.

---

## Contributing

- All Python scripts must follow PEP 8 style guidelines.
- All notebooks must have a description cell at the top explaining the objective, inputs, and expected outputs.
- Do not commit data files. Add any new data directories to `.gitignore`.
- Use descriptive variable names. Avoid single-letter variable names outside of mathematical equations.
