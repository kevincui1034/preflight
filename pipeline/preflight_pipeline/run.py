"""Local end-to-end runner (development harness for the RocketRide stages).

    python -m preflight_pipeline.run --repo ../fixtures/demo-service \
        --project-id demo --review-id r1 [--no-graph] [--deep]

Stages mirror the RocketRide pipeline exactly; this runner exists so the
whole review can be exercised before (and independently of) the cloud
deploy. Prints the findings JSON to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .extract import scan_repo
from .findings import compose_findings, to_graph_records
from .judge import judge_review


def run_review(
    repo: Path,
    project_id: str,
    review_id: str,
    *,
    use_graph: bool = True,
    deep: bool = False,
) -> dict:
    scan = scan_repo(repo)
    graph_results = None
    if use_graph:
        from .graph import GraphClient  # import here: static mode needs no driver

        with GraphClient() as client:
            client.ensure_constraints()
            client.load_review(project_id, review_id, "deep" if deep else "free", scan)
            graph_results = client.run_traversals(review_id)
            findings = compose_findings(project_id, scan, graph_results)
            model_id = None
            if deep:
                extras, model_id = judge_review(scan, graph_results, findings)
                findings += extras
            client.record_findings(
                review_id, to_graph_records(review_id, project_id, findings)
            )
    else:
        findings = compose_findings(project_id, scan, None)
        model_id = None
        if deep:
            extras, model_id = judge_review(scan, None, findings)
            findings += extras
    return {
        "review_id": review_id,
        "project_id": project_id,
        "kind": "deep" if deep else "free",
        "model_id": model_id,
        "graph": graph_results is not None,
        "findings": findings,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Preflight review locally")
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--project-id", default="demo")
    parser.add_argument("--review-id", default="r1")
    parser.add_argument("--no-graph", action="store_true", help="static-only (no Neo4j)")
    parser.add_argument("--deep", action="store_true", help="include the Nebius judge")
    args = parser.parse_args()
    result = run_review(
        args.repo,
        args.project_id,
        args.review_id,
        use_graph=not args.no_graph,
        deep=args.deep,
    )
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
