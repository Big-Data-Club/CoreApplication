# Output directory

Model-generated outputs go here. This directory is NOT committed to git.

## Directory layout

```
output/
|-- slates/              Recommendation slate CSV files (one per model)
|-- evaluation/          Metric summary CSV and HTML reports
```

## File naming convention

- Slates: `<model_name>_slates.csv`
- Evaluation: `<model_name>_metrics.csv`

## Expected slate schema

```
user_id, rank, recommended_node_id, model
42,      1,    105,                 srd_gru4rec
42,      2,    112,                 srd_gru4rec
...
```

## Expected evaluation schema

```
model,      precision@5, recall@5, ndcg@5, ild,  novelty
heuristic,  0.40,        0.25,     0.38,   0.72, 1.20
srd,        0.42,        0.28,     0.41,   0.48, 1.85
divkg,      0.45,        0.31,     0.44,   0.35, 2.10
```
