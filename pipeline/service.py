"""HTTP entry for the RocketRide pipeline — POST /review.

Body: {review_id, repo_url, kind}. Runs the stages (extract → graph →
traversals → findings → judge if deep) and POSTs results to the
Butterbase callback. Env: CALLBACK_URL, CALLBACK_KEY, NEO4J_*, NEBIUS_*.
Local dev: uvicorn service:app --port 8808 (from pipeline/).
GitHub URLs are shallow-cloned; file:// or local paths used directly
(the fixture path for demos without network).
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import FastAPI

from preflight_pipeline.extract import scan_repo
from preflight_pipeline.findings import compose_findings, to_graph_records
from preflight_pipeline.judge import judge_review

app = FastAPI(title="preflight-review")


def _checkout(repo_url: str, tmp: str) -> Path:
    local = Path(repo_url.removeprefix("file://"))
    if local.exists():
        return local
    subprocess.run(
        ["git", "clone", "--depth", "2", repo_url, tmp],
        check=True, capture_output=True, timeout=120,
    )
    return Path(tmp)


@app.post("/review")
def review(body: dict) -> dict:
    review_id = body["review_id"]
    kind = body.get("kind", "free")
    payload: dict = {"review_id": review_id, "status": "complete"}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = _checkout(body["repo_url"], tmp)
            scan = scan_repo(root)
            graph_results, model_id = None, None
            try:
                from preflight_pipeline.graph import GraphClient

                with GraphClient() as gc:
                    gc.ensure_constraints()
                    gc.load_review(body.get("project_id", "demo"), review_id, kind, scan)
                    graph_results = gc.run_traversals(review_id)
                    findings = compose_findings(body.get("project_id", "demo"), scan, graph_results)
                    if kind == "deep":
                        extras, model_id = judge_review(scan, graph_results, findings)
                        findings += extras
                    gc.record_findings(review_id, to_graph_records(review_id, body.get("project_id", "demo"), findings))
            except Exception:
                findings = compose_findings(body.get("project_id", "demo"), scan, None)
                if kind == "deep":
                    extras, model_id = judge_review(scan, None, findings)
                    findings += extras
            payload["findings"] = findings
            payload["model_id"] = model_id
            blast = (graph_results or {}).get("blast_radius") or []
            if blast:
                payload["blast_radius"] = max(r["blast_radius"] for r in blast)
    except Exception as exc:
        payload.update(status="failed", findings=[], error=str(exc)[:200])
    httpx.post(
        os.environ["CALLBACK_URL"],
        headers={"X-Callback-Key": os.environ["CALLBACK_KEY"]},
        json=payload,
        timeout=30,
    )
    return {"ok": True, "findings": len(payload.get("findings", []))}
