# Preflight — project context & decision log

*HackwithBay 3.0, 2026-07-07, AWS Builder Loft SF. Theme: "Thoughtful
Agents for Productivity." Built from scratch in one day.*

## What it is

Paste a repo → an agent tells you whether it will survive a deploy, with
**graph evidence instead of vibes**. Free review = static checks + graph
traversals. Deep review (costs 1 credit) = adds an LLM judge (Nebius) and
proof-by-execution (Daytona sandbox runs the repo's own tests).

Positioning (carried from the Proofloop research): *correctness, not
security* — "your guardrails stop the dangerous command; Preflight
catches the broken one." Nobody guards correctness **at the deploy
moment**.

## Mandatory sponsor requirements → where they live

| Requirement | Implementation | Why it's load-bearing, not bolted on |
| --- | --- | --- |
| Butterbase db+auth+payments | App `app_pwpiaegbqw20`: 4 RLS-isolated tables, JWT-gated functions, Stripe Connect credit packs | The product IS the backend; the paywall gates real functionality (deep reviews) |
| Neo4j property graph, actively traversed | Code property graph (docs/graph-model.md); Q1 blast radius, Q2 load-bearing fan-in, Q3 prod env gap, Q4 past-failure proximity | Every finding is derived from or ranked by a traversal — findings render their hop paths |
| RocketRide Cloud pipeline | Review stages (extract → graph → traversals → judge → callback) wrapped as a RocketRide pipeline, deployed to cloud.rocketride.ai | Every review the dashboard triggers is a call to that endpoint |
| Daytona (bonus) | Deep review clones the repo in a sandbox and runs its tests; real output attached as evidence | "Proof by execution, not model opinion" |
| Cognee OSS on Neo4j (bonus) | Episodic memory: recall prior findings on re-review; human reject → forget | Kept in a separate namespace so it's never confused with OUR Neo4j usage |
| Nebius (our choice) | Deep-review judge via OpenAI-compatible chat/completions | Sponsor-stack inference; model id recorded per finding |

## Key decisions & reasoning

1. **Graph-brained product choice.** We picked a deploy-readiness agent
   *because* its core questions (how far does a change reach? which files
   are hubs? did this area fail before?) are relationship questions —
   making Neo4j structurally central satisfies the "not a glorified KV
   store" judging bar by construction.
2. **Graph model committed before any pipeline code** (commit `7675b70`)
   so git history *proves* the sponsor-required ordering.
3. **Stages are pure functions** (`pipeline/preflight_pipeline/`): scan →
   dict, graph → dict, findings → list. Reason: they wrap into whatever
   node primitive the RocketRide VS Code extension scaffolds, without a
   rewrite; `run.py` is the local dev harness (`--no-graph` static mode
   works with zero infra).
4. **Fixture over live repo** (`fixtures/demo-service`): every finding
   fires deterministically on stage — missing prod env var
   (payments.py:10), hardcoded secret (notifications.py:9), failing
   discount test, core.py hub (fan-in 5), `.preflight-changed` manifest
   pins the changed set. Wifi cannot break the core demo.
5. **Butterbase auth-edge finding** (empirical): the `/fn/` JWT edge
   rejects `bb_sk` service keys — even with app access_mode public. So
   `review-callback` uses the documented `auth: "none"` + manual
   shared-secret guard (`X-Callback-Key`), which also gives it the
   service-role DB access the cross-user findings insert needs.
   User-facing functions stay `auth: "required"` (end-user JWT, RLS).
   App access_mode is `public` (per-function auth + RLS still protect
   everything; `authenticated` mode blocked the callback path entirely).
6. **Credits via ledger, not a balance column**: `credits_ledger` rows
   (+5 purchase / −1 deep review) — auditable, idempotent
   (`ctx.idempotency.claim` per Stripe order), and demo-friendly.
7. **Judge is optional-graceful**: Nebius errors → template findings
   only; a review never fails because the model did. Same philosophy as
   the fixture: the demo must not depend on the network being kind.

## Live infrastructure

- Butterbase app `app_pwpiaegbqw20` — API
  `https://api.butterbase.ai/v1/app_pwpiaegbqw20`, frontend slot
  `https://preflight.butterbase.dev`.
- Functions: `create-review` (JWT), `review-callback` (X-Callback-Key),
  `claim-credits` (JWT). Secrets in `.env` (gitignored) — Butterbase
  service key, callback secret; Neo4j/Nebius/RocketRide/Daytona pending.

## Remaining (see PLAN-hackwithbay.md in the judge repo for schedule)

Dashboard frontend → RocketRide wrap + cloud deploy (user account
pending) → Aura full-graph run (creds pending) → Stripe Connect
onboarding + credit product → Daytona → Cognee → submit by 4:30 PM via
`prep_and_submit_hackathon_entry`.
