"""Neo4j code property graph — upsert + the four review traversals.

The model is docs/graph-model.md verbatim. Every finding Preflight
raises is derived from, or ranked by, one of these queries.
"""

from __future__ import annotations

import os

from neo4j import GraphDatabase

HUB_THRESHOLD = 3
BLAST_HOPS = 3

CONSTRAINTS = [
    "CREATE CONSTRAINT file_key IF NOT EXISTS FOR (f:File) REQUIRE f.key IS UNIQUE",
    "CREATE CONSTRAINT envvar_key IF NOT EXISTS FOR (v:EnvVar) REQUIRE v.key IS UNIQUE",
    "CREATE CONSTRAINT review_id IF NOT EXISTS FOR (r:Review) REQUIRE r.id IS UNIQUE",
    "CREATE CONSTRAINT finding_id IF NOT EXISTS FOR (x:Finding) REQUIRE x.id IS UNIQUE",
]


class GraphClient:
    def __init__(self, uri: str | None = None, username: str | None = None, password: str | None = None):
        self.driver = GraphDatabase.driver(
            uri or os.environ["NEO4J_URI"],
            auth=(
                username or os.environ.get("NEO4J_USERNAME", "neo4j"),
                password or os.environ["NEO4J_PASSWORD"],
            ),
        )

    def close(self) -> None:
        self.driver.close()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.close()

    def _run(self, query: str, **params) -> list[dict]:
        with self.driver.session() as session:
            return [dict(record) for record in session.run(query, **params)]

    def ensure_constraints(self) -> None:
        for statement in CONSTRAINTS:
            self._run(statement)

    # -- upsert ------------------------------------------------------------

    def load_review(self, project_id: str, review_id: str, kind: str, scan: dict) -> None:
        """MERGE the scan into the graph under this project + review."""
        fk = lambda path: f"{project_id}#{path}"  # noqa: E731
        vk = lambda name: f"{project_id}#{name}"  # noqa: E731
        self._run(
            "MERGE (p:Project {id: $pid}) "
            "MERGE (r:Review {id: $rid}) "
            "SET r.project_id = $pid, r.kind = $kind, r.created_at = datetime() "
            "MERGE (r)-[:OF]->(p)",
            pid=project_id, rid=review_id, kind=kind,
        )
        self._run(
            "UNWIND $files AS file "
            "MERGE (f:File {key: file.key}) "
            "SET f.path = file.path, f.project_id = $pid "
            "WITH f MATCH (p:Project {id: $pid}) MERGE (p)-[:HAS_FILE]->(f)",
            pid=project_id,
            files=[{"key": fk(p), "path": p} for p in scan["files"]],
        )
        self._run(
            "UNWIND $edges AS e "
            "MATCH (a:File {key: e.src}), (b:File {key: e.dst}) "
            "MERGE (a)-[:IMPORTS]->(b)",
            edges=[{"src": fk(i["src"]), "dst": fk(i["dst"])} for i in scan["imports"]],
        )
        self._run(
            "UNWIND $reads AS rd "
            "MATCH (f:File {key: rd.file}) "
            "MERGE (v:EnvVar {key: rd.vkey}) SET v.name = rd.name "
            "MERGE (f)-[r:READS]->(v) SET r.line = rd.line",
            reads=[
                {"file": fk(r["file"]), "vkey": vk(r["name"]), "name": r["name"], "line": r["line"]}
                for r in scan["env_reads"]
            ],
        )
        self._run(
            "MERGE (e:Env {name: 'prod'}) "
            "WITH e UNWIND $names AS name "
            "MERGE (v:EnvVar {key: $pid + '#' + name}) SET v.name = name "
            "MERGE (v)-[:SET_IN]->(e)",
            pid=project_id, names=scan["prod_env"],
        )
        self._run(
            "MATCH (r:Review {id: $rid}) "
            "UNWIND $keys AS key MATCH (f:File {key: key}) "
            "MERGE (r)-[:CHANGED]->(f)",
            rid=review_id, keys=[fk(p) for p in scan["changed"]],
        )

    def record_findings(self, review_id: str, findings: list[dict]) -> None:
        """Persist findings as nodes so Q4 can ground future reviews."""
        self._run(
            "MATCH (r:Review {id: $rid}) "
            "UNWIND $findings AS x "
            "MERGE (n:Finding {id: x.id}) "
            "SET n.class = x.class, n.detail = x.detail, n.severity = x.severity "
            "MERGE (r)-[:PRODUCED]->(n) "
            "WITH n, x WHERE x.file_key IS NOT NULL "
            "MATCH (f:File {key: x.file_key}) MERGE (n)-[:ON]->(f)",
            rid=review_id, findings=findings,
        )

    # -- the four traversals -------------------------------------------------

    def q1_blast_radius(self, review_id: str) -> list[dict]:
        return self._run(
            "MATCH (r:Review {id: $rid})-[:CHANGED]->(f:File) "
            f"OPTIONAL MATCH (dependent:File)-[:IMPORTS*1..{BLAST_HOPS}]->(f) "
            "RETURN f.path AS changed, "
            "collect(DISTINCT dependent.path) AS impacted, "
            "count(DISTINCT dependent) AS blast_radius "
            "ORDER BY blast_radius DESC",
            rid=review_id,
        )

    def q2_load_bearing(self, review_id: str, hub_threshold: int = HUB_THRESHOLD) -> list[dict]:
        return self._run(
            "MATCH (r:Review {id: $rid})-[:CHANGED]->(f:File) "
            "OPTIONAL MATCH (dep:File)-[:IMPORTS]->(f) "
            "WITH f, count(dep) AS fan_in "
            "RETURN f.path AS path, fan_in, fan_in >= $threshold AS load_bearing "
            "ORDER BY fan_in DESC",
            rid=review_id, threshold=hub_threshold,
        )

    def q3_env_gap(self, review_id: str) -> list[dict]:
        return self._run(
            "MATCH (r:Review {id: $rid})-[:CHANGED]->(f:File) "
            "MATCH (f)-[read:READS]->(v:EnvVar) "
            "WHERE NOT (v)-[:SET_IN]->(:Env {name: 'prod'}) "
            "RETURN f.path AS path, read.line AS line, v.name AS missing_var",
            rid=review_id,
        )

    def q4_past_failures(self, review_id: str) -> list[dict]:
        return self._run(
            "MATCH (r:Review {id: $rid})-[:CHANGED]->(f:File) "
            "MATCH (prior:Review)-[:PRODUCED]->(old:Finding)-[:ON]->(g:File) "
            "WHERE prior.id <> $rid AND (g = f OR (f)-[:IMPORTS*1..2]-(g)) "
            "RETURN DISTINCT old.class AS class, old.detail AS detail, "
            "g.path AS path, prior.id AS seen_in "
            "ORDER BY seen_in DESC",
            rid=review_id,
        )

    def run_traversals(self, review_id: str) -> dict:
        return {
            "blast_radius": self.q1_blast_radius(review_id),
            "load_bearing": self.q2_load_bearing(review_id),
            "env_gap": self.q3_env_gap(review_id),
            "past_failures": self.q4_past_failures(review_id),
        }
