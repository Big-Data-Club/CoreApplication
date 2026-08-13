# BDC Hub Team Assets

This catalogue is the entry point for shared delivery assets. It identifies the
source of truth and the team that must be involved before a change crosses a
boundary.

| Team | Asset | Location | Use / ownership |
|---|---|---|---|
| BA/Product | BA handbook | [teams/BA_HANDBOOK.md](teams/BA_HANDBOOK.md) | journeys, acceptance criteria, scope decisions |
| Developers | Developer guide | [DEVELOPER_GUIDE.md](teams/DEVELOPER_GUIDE.md) | service map, local development, test workflow |
| Developers / Performance | Scalability and file-delivery note | [SCALABILITY_AND_FILE_DELIVERY_OPTIMIZATIONS.md](optimization/SCALABILITY_AND_FILE_DELIVERY_OPTIMIZATIONS.md) | user/course pagination, PDF delivery, rollout and measurement |
| Developers | Kubernetes developer guide | [KUBERNETES_DEVELOPER_GUIDE.md](teams/KUBERNETES_DEVELOPER_GUIDE.md) | infrastructure/application layer map, K3s inspection, sandbox quick start |
| Data/ML | Data platform guide | [DATA_PLATFORM.md](DATA_PLATFORM.md) | Kafka contracts, Lakehouse, quality and access rules |
| Data/ML + AI + Product | Recommender and conversational recommender | [recommender/README.md](recommender/README.md) | product use, ranking policy, conversational flow, feedback loop and roadmap |
| Data/ML | Offline analytics workspace | `da-analytics/` submodule | notebooks, reproducible model experiments, Gold inputs |
| AI | Agent/AI implementation | `ai-service/app/agents/`, `ai-service/app/worker/` | runtime agent and asynchronous job behaviour |
| Backend | API source and migrations | service `cmd/`, `internal/`, `app/`, `migrations/` | executable implementation source of truth |
| Product / Backend / Frontend | Virtual STEM Lab proposal | [VIRTUAL_STEM_LAB.md](proposals/VIRTUAL_STEM_LAB.md) | target journeys, scientific-model boundaries, rollout gates |
| Backend / QA | Virtual STEM foundation API | [VIRTUAL_STEM_API.md](../lab-service/docs/VIRTUAL_STEM_API.md) | implemented version, run, trial and evidence contracts |
| Frontend | UI repository | `frontend/` submodule | Next.js UI, BFF/route handlers; follow submodule rules |
| QA | Service tests | `*_service` test directories | regression and contract coverage |
| QA/DevOps | k6 performance assets | [performance-tests/](../performance-tests/README.md) | approved smoke/load workflow and test Jobs |
| DevOps | Deployment and operations | [DEVOPS_RUNBOOK.md](teams/DEVOPS_RUNBOOK.md) | K3s access, CI/CD, troubleshooting, incident process |
| DevOps | Kubernetes source | `k3s/` | manifests, observability, Helm values |
| All contributors | Contribution policy | [../CONTRIBUTING.md](../CONTRIBUTING.md) | PR, tests, data/event documentation and review rules |
| Coding agents | Repository skills | `.agent/skills/` | implementation-aware working constraints |
| Architecture | Decision records | `adr/` | durable rationale and consequences |

## Asset selection rules

1. Source code and deployed manifests win over prose if they disagree; correct
   the prose in the same change.
2. Work in `frontend/` or `da-analytics/` belongs to their submodule repository.
   Do not mix a submodule feature implementation with a parent-repository
   documentation-only change without making the pointer update explicit.
3. API, Kafka, Lakehouse, and deployment changes need owners from both sides of
   the boundary. The pull request should name them.
4. Test data, dashboard snapshots, model outputs, and credentials are not
   general-purpose assets. Store or share them only through approved internal
   channels and never commit them here.
