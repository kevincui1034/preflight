# Preflight graph model (Neo4j)

The agent's brain is a property graph of the reviewed codebase. Every
finding Preflight raises is derived from, or ranked by, a traversal of
this graph — sketched here, per the hackathon requirement, before any
pipeline code exists.

## Nodes

| Label | Properties | Meaning |
| --- | --- | --- |
| `Project` | `id`, `repo_url` | One reviewed repository |
| `File` | `key` (`<project_id>#<path>`, unique), `path`, `language` | A source file |
| `EnvVar` | `key` (`<project_id>#<name>`, unique), `name` | An environment variable the code reads |
| `Env` | `name` (`prod` \| `staging`) | A deploy target environment |
| `Review` | `id` (unique), `project_id`, `head_sha`, `kind` (`free` \| `deep`), `created_at` | One review run |
| `Finding` | `id` (unique), `class`, `severity`, `confidence`, `detail`, `model_id` | One raised issue (model_id records the Nebius model for deep findings) |

## Relationships

```
(Project)-[:HAS_FILE]->(File)
(File)-[:IMPORTS]->(File)          // static import/require edges
(File)-[:READS]->(EnvVar)          // env access at file:line (line on the edge)
(EnvVar)-[:SET_IN]->(Env)          // known-configured in that environment
(Review)-[:OF]->(Project)
(Review)-[:CHANGED]->(File)        // files touched at the reviewed head
(Review)-[:PRODUCED]->(Finding)
(Finding)-[:ON]->(File)
```

## Constraints

```cypher
CREATE CONSTRAINT file_key IF NOT EXISTS
  FOR (f:File) REQUIRE f.key IS UNIQUE;
CREATE CONSTRAINT envvar_key IF NOT EXISTS
  FOR (v:EnvVar) REQUIRE v.key IS UNIQUE;
CREATE CONSTRAINT review_id IF NOT EXISTS
  FOR (r:Review) REQUIRE r.id IS UNIQUE;
CREATE CONSTRAINT finding_id IF NOT EXISTS
  FOR (x:Finding) REQUIRE x.id IS UNIQUE;
```

## The four traversals the agent runs per review

**Q1 — blast radius.** How far does this change reach through the import
graph? Rendered on every finding ("reaches 7 files through 3 hops").

```cypher
MATCH (r:Review {id: $review_id})-[:CHANGED]->(f:File)
OPTIONAL MATCH (dependent:File)-[:IMPORTS*1..3]->(f)
RETURN f.path AS changed,
       collect(DISTINCT dependent.path) AS impacted,
       count(DISTINCT dependent) AS blast_radius
ORDER BY blast_radius DESC
```

**Q2 — load-bearing ranking.** Fan-in over `IMPORTS`: findings on hub
files get a severity boost.

```cypher
MATCH (r:Review {id: $review_id})-[:CHANGED]->(f:File)
OPTIONAL MATCH (dep:File)-[:IMPORTS]->(f)
WITH f, count(dep) AS fan_in
RETURN f.path, fan_in, fan_in >= $hub_threshold AS load_bearing
ORDER BY fan_in DESC
```

**Q3 — prod env gap.** A changed file reads an env var that no known
`prod` configuration sets → missing-env finding at the exact read site.

```cypher
MATCH (r:Review {id: $review_id})-[:CHANGED]->(f:File)
MATCH (f)-[read:READS]->(v:EnvVar)
WHERE NOT (v)-[:SET_IN]->(:Env {name: 'prod'})
RETURN f.path, read.line AS line, v.name AS missing_var
```

**Q4 — past-failure proximity (relationship-based retrieval).** Prior
findings on, or within 2 import-hops of, the changed files ground new
findings: "this area failed before."

```cypher
MATCH (r:Review {id: $review_id})-[:CHANGED]->(f:File)
MATCH (prior:Review)-[:PRODUCED]->(old:Finding)-[:ON]->(g:File)
WHERE prior.id <> $review_id
  AND (g = f OR (f)-[:IMPORTS*1..2]-(g))
RETURN DISTINCT old.class, old.detail, g.path, prior.id AS seen_in
ORDER BY prior.id DESC
```

## Namespace note (Cognee bonus)

Cognee (OSS) is configured against this same Neo4j instance as its graph
backend, under its own labels. The code property graph above — and the
four traversals — are Preflight's own Neo4j usage; Cognee's memory graph
is the agent's episodic experience and is kept visibly distinct.
