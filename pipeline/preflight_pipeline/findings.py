"""Findings composer — graph results (or static fallback) → findings.

Every finding cites evidence: file:line plus the graph path that produced
or ranked it. Severity: "error" when the finding sits on a load-bearing
file (Q2), else "warning".
"""

from __future__ import annotations

SECRET_DETAIL = "Hardcoded credential committed in the tree"


def _blast_for(graph: dict | None, path: str) -> dict | None:
    if not graph:
        return None
    for row in graph.get("blast_radius", []):
        if row["changed"] == path:
            return {"blast_radius": row["blast_radius"], "impacted": row["impacted"][:10]}
    return None


def _load_bearing_paths(graph: dict | None) -> set[str]:
    if not graph:
        return set()
    return {row["path"] for row in graph.get("load_bearing", []) if row["load_bearing"]}


def _seen_before(graph: dict | None, path: str) -> list[dict]:
    if not graph:
        return []
    return [
        {"class": row["class"], "path": row["path"], "seen_in": row["seen_in"]}
        for row in graph.get("past_failures", [])
        if row["path"] == path
    ][:3]


def compose_findings(
    project_id: str, scan: dict, graph: dict | None
) -> list[dict]:
    """Static + graph-derived findings. ``graph=None`` = static-only mode
    (no Neo4j reachable): env gaps fall back to the prod-manifest diff and
    no blast/severity evidence is attached."""
    hubs = _load_bearing_paths(graph)
    findings: list[dict] = []

    if graph is not None:
        gaps = [
            {"file": row["path"], "line": row["line"], "name": row["missing_var"]}
            for row in graph.get("env_gap", [])
        ]
    else:
        prod = set(scan.get("prod_env", []))
        gaps = [
            read
            for read in scan["env_reads"]
            if read["name"] not in prod and read["file"] in scan["changed"]
        ]

    for gap in gaps:
        evidence = {
            "query": "q3_env_gap" if graph is not None else "static_prod_manifest_diff",
            "prod_manifest": scan.get("prod_manifest"),
        }
        blast = _blast_for(graph, gap["file"])
        if blast:
            evidence["blast"] = blast
        seen = _seen_before(graph, gap["file"])
        if seen:
            evidence["seen_before"] = seen
        findings.append(
            {
                "class": "missing_env_var",
                "severity": "error" if gap["file"] in hubs else "warning",
                "confidence": 0.95,
                "detail": (
                    f"{gap['name']} is read at {gap['file']}:{gap['line']} but the "
                    "production manifest does not set it — the first request "
                    "after deploy will crash."
                ),
                "file_path": gap["file"],
                "line": gap["line"],
                "graph_evidence": evidence,
            }
        )

    for secret in scan["secrets"]:
        evidence = {"query": "static_secret_scan"}
        blast = _blast_for(graph, secret["file"])
        if blast:
            evidence["blast"] = blast
        findings.append(
            {
                "class": "hardcoded_secret",
                "severity": "error" if secret["file"] in hubs else "warning",
                "confidence": 0.9,
                "detail": f"{SECRET_DETAIL} at {secret['file']}:{secret['line']}.",
                "file_path": secret["file"],
                "line": secret["line"],
                "graph_evidence": evidence,
            }
        )

    # Changed hub files are a finding in themselves: wide blast radius.
    for path in sorted(hubs):
        blast = _blast_for(graph, path) or {}
        findings.append(
            {
                "class": "load_bearing_change",
                "severity": "warning",
                "confidence": 0.8,
                "detail": (
                    f"{path} is load-bearing: this change reaches "
                    f"{blast.get('blast_radius', '?')} file(s) through the import "
                    "graph — review with extra care."
                ),
                "file_path": path,
                "line": 1,
                "graph_evidence": {"query": "q1_blast_radius+q2_load_bearing", **({"blast": blast} if blast else {})},
            }
        )

    return findings


def to_graph_records(review_id: str, project_id: str, findings: list[dict]) -> list[dict]:
    """Shape findings for GraphClient.record_findings (feeds future Q4)."""
    return [
        {
            "id": f"{review_id}#{index}",
            "class": f["class"],
            "detail": f["detail"],
            "severity": f["severity"],
            "file_key": f"{project_id}#{f['file_path']}" if f.get("file_path") else None,
        }
        for index, f in enumerate(findings)
    ]
