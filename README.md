# Preflight

Paste a repo, and an agent tells you whether it will survive a deploy —
with graph evidence instead of vibes. Correctness, not security: your
guardrails stop the dangerous command; Preflight catches the broken one.

Built from scratch at **HackwithBay 3.0** (2026-07-07, AWS Builder Loft
SF) for the theme *"Thoughtful Agents for Productivity."*

## How it works

1. Sign in and point Preflight at a repository (Butterbase: auth, db,
   billing — deep reviews cost credits).
2. The dashboard calls the review pipeline running as a managed endpoint
   on **cloud.rocketride.ai**.
3. The pipeline builds a **code property graph in Neo4j** (imports,
   env reads, deploy targets, past findings) and derives every finding
   from a traversal: blast radius, load-bearing fan-in, prod env gaps,
   and past-failure proximity — see [docs/graph-model.md](docs/graph-model.md).
4. **Deep reviews** add a judge (an open model on **Nebius AI Studio**)
   and proof by execution: a **Daytona** sandbox clones the repo and
   actually runs its tests, attaching real output as evidence.
5. The agent remembers: **Cognee** (open source, on the same Neo4j)
   recalls prior findings on re-review — and forgets the ones a human
   rejects.

## Stack

| Piece | Tech |
| --- | --- |
| Backend, auth, payments, frontend hosting | Butterbase |
| Code property graph | Neo4j (Aura) |
| Review pipeline (managed endpoint) | RocketRide Cloud |
| Deep-review judge | Nebius AI Studio |
| Execution sandbox (bonus) | Daytona |
| Agent memory (bonus) | Cognee OSS |

## Repo layout

- `docs/graph-model.md` — the graph schema + the four Cypher traversals
  (committed first, before any pipeline code)
- `pipeline/` — the RocketRide review pipeline
- `app/` — Butterbase functions + dashboard
- `fixtures/demo-service` — deterministic demo repo (missing prod env
  var, hardcoded secret, failing test, one load-bearing hub module)
