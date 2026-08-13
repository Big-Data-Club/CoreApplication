# Virtual STEM experiment API (foundation)

Status: implemented foundation. Plant and robot simulation commands are not part of this slice.

All routes use the existing `/api/v1` prefix and JWT middleware.

## Lifecycle

```text
PLANT/ROBOT lab
  -> create immutable DRAFT version
  -> validate (DRAFT -> VALIDATED)
  -> publish (VALIDATED -> PUBLISHED; older version -> SUPERSEDED)
  -> enrolled learner creates idempotent run
  -> learner creates deterministic trials
  -> learner appends ordered evidence
  -> teacher lists runs and reads each evidence timeline
```

The legacy `POST /labs/{labId}/publish` rejects `PLANT` and `ROBOT` labs. These labs must publish a validated version.

## Authoring routes

| Method | Path | Role | Result |
|---|---|---|---|
| `POST` | `/labs/{labId}/versions` | Teacher/Admin | Store an immutable definition snapshot |
| `GET` | `/labs/{labId}/versions` | Lab owner/Admin | List immutable versions newest-first so the editor can resume after reload |
| `GET` | `/lab-versions/{versionId}/definition` | Owner/Admin or enrolled learner for published version | Read snapshot and hash |
| `POST` | `/lab-versions/{versionId}/validate` | Teacher/Admin | Return structured errors/warnings and mark valid version `VALIDATED` |
| `POST` | `/lab-versions/{versionId}/publish` | Teacher/Admin | Publish version and supersede the previous published version |

Example definition:

```json
{
  "definition": {
    "domain": "PLANT",
    "inquiry_level": "GUIDED",
    "workflow_schema_version": 1,
    "model_version": "plant-lite-1.0.0",
    "learning_objectives": [
      "Explain how irrigation affects plant biomass"
    ],
    "config": {
      "species": "brassica"
    },
    "nodes": [
      {"key":"predict","type":"PREDICTION","title":"Predict","required_evidence":["prediction"],"order_hint":0},
      {"key":"run","type":"RUN","title":"Run experiment","required_evidence":[],"order_hint":1},
      {"key":"analyze","type":"ANALYZE","title":"Analyze data","required_evidence":["chart"],"order_hint":2},
      {"key":"explain","type":"EXPLAIN","title":"Write CER","required_evidence":["cer"],"order_hint":3},
      {"key":"iterate","type":"ITERATE","title":"Improve design","required_evidence":["change_reason"],"order_hint":4},
      {"key":"reflect","type":"REFLECT","title":"Reflect","required_evidence":["reflection"],"order_hint":5}
    ],
    "edges": [
      {"from":"predict","to":"run","condition_expression":"always","priority":0},
      {"from":"run","to":"analyze","condition_expression":"always","priority":0},
      {"from":"analyze","to":"explain","condition_expression":"always","priority":0},
      {"from":"explain","to":"iterate","condition_expression":"always","priority":0},
      {"from":"iterate","to":"reflect","condition_expression":"always","priority":0}
    ],
    "variables": [
      {"key":"irrigation","display_name":"Irrigation","role":"INDEPENDENT","data_type":"NUMBER","unit":"mL/day","source_id":"fao56"},
      {"key":"biomass","display_name":"Biomass","role":"DEPENDENT","data_type":"NUMBER","unit":"g","source_id":"plant-card"},
      {"key":"temperature","display_name":"Temperature","role":"CONTROLLED","data_type":"NUMBER","unit":"Cel","source_id":"plant-card"}
    ]
  }
}
```

The foundation accepts only `always` edges. Executable branching expressions wait for a versioned, sandboxed expression language; raw expressions must never be passed to SQL or a shell.

Publish validation requires:

- one learning objective;
- one reachable workflow with exactly one start and at least one terminal node;
- `PREDICTION`, `RUN`, `ANALYZE`, `EXPLAIN`, and `ITERATE` steps;
- required evidence for evidence-producing STEM steps;
- independent, dependent, and controlled variables;
- units for numeric variables (`1` means dimensionless).

## Learner and teacher routes

| Method | Path | Access | Result |
|---|---|---|---|
| `POST` | `/lab-versions/{versionId}/runs` | Enrolled learner or owner preview | Create/retrieve a run by idempotency key |
| `GET` | `/labs/{labId}/published-version` | Enrolled learner or owner preview | Resolve the pinned published definition used by the workspace |
| `GET` | `/runs/{runId}` | Run owner, lab owner, Admin | Read current run state |
| `POST` | `/runs/{runId}/trials` | Run owner | Create next numbered trial with fixed/random seed |
| `POST` | `/runs/{runId}/evidence` | Run owner | Append an idempotent, ordered event |
| `GET` | `/runs/{runId}/events?after_seq=0&limit=200` | Run owner, lab owner, Admin | Read timeline for replay |
| `POST` | `/runs/{runId}/complete` | Run owner | Complete only after every required evidence object exists |
| `GET` | `/labs/{labId}/runs?status=ACTIVE&page=1&page_size=20` | Lab owner/Admin | List learners, current steps and trial counts |

Create a run:

```json
{
  "idempotency_key": "browser-session-0191f8d8"
}
```

Create a deterministic trial:

```json
{
  "seed": 42,
  "config_snapshot": {
    "irrigation": 70,
    "temperature": 25
  }
}
```

Omit `seed` for a cryptographically generated non-negative 53-bit seed. The JSON-safe response always returns the chosen seed and pinned model version.

Append evidence:

```json
{
  "client_event_id": "2e211d3e-f3ce-4d28-92be-b9d8db37b211",
  "trial_id": 1452,
  "workflow_node_key": "analyze",
  "verb": "analyzed",
  "object": {
    "type": "chart",
    "id": "biomass-by-day"
  },
  "result": {
    "artifact_id": "chart-9f3a"
  },
  "context": {
    "model_version": "plant-lite-1.0.0"
  },
  "sim_time_ms": 1036800000
}
```

`client_event_id` is unique inside a run. A retry returns the original event without consuming another `seq_no`. Appends are serialized per run. Evidence payloads are limited to 64 KiB; large code, notebooks and telemetry will use versioned artifacts/object storage in a later slice.

Supported evidence verbs in this version:

```text
answered_question, predicted, designed_experiment, changed_variable,
started_trial, paused_trial, resumed_trial, observed, measured, analyzed,
explained, iterated, reflected, code_saved, checkpoint_completed
```

## Persistence and recovery

- `lab_versions.definition_snapshot` and `definition_hash` make published authoring state reproducible.
- Normalized workflow/variable rows support server-side validation and later execution.
- `evidence_events` is append-only at the API boundary and ordered by `(run_id, seq_no)`.
- A trial foreign key guarantees that evidence cannot reference a trial from another run.
- The operational database remains the source of truth. Kafka analytics publication is intentionally not implemented yet, so a broker outage cannot fail learner evidence writes.
- If rollout fails, disable the experiment routes and preserve all version/run/evidence rows. Do not recover by deleting learner evidence.
