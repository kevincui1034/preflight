from pathlib import Path

from preflight_pipeline.extract import scan_repo
from preflight_pipeline.findings import compose_findings, to_graph_records
from preflight_pipeline.judge import _parse

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "demo-service"


def test_static_only_findings_fire():
    scan = scan_repo(FIXTURE)
    findings = compose_findings("demo", scan, None)
    classes = {f["class"] for f in findings}
    assert classes == {"missing_env_var", "hardcoded_secret"}
    env_gap = next(f for f in findings if f["class"] == "missing_env_var")
    # STRIPE_API_KEY (changed file, absent from prod manifest) — and NOT
    # DATABASE_URL (present in the manifest, and db.py isn't changed).
    assert "STRIPE_API_KEY" in env_gap["detail"]
    assert env_gap["file_path"] == "payments.py"
    assert env_gap["graph_evidence"]["prod_manifest"] == "deploy/prod.env"


def test_graph_results_boost_and_decorate():
    scan = scan_repo(FIXTURE)
    graph = {
        "blast_radius": [
            {"changed": "payments.py", "impacted": ["app.py", "workers.py"], "blast_radius": 2},
            {"changed": "core.py", "impacted": ["app.py", "payments.py", "workers.py", "reports.py", "notifications.py"], "blast_radius": 5},
        ],
        "load_bearing": [
            {"path": "core.py", "fan_in": 5, "load_bearing": True},
            {"path": "payments.py", "fan_in": 1, "load_bearing": False},
        ],
        "env_gap": [{"path": "payments.py", "line": 10, "missing_var": "STRIPE_API_KEY"}],
        "past_failures": [
            {"class": "missing_env_var", "detail": "seen", "path": "payments.py", "seen_in": "r0"}
        ],
    }
    findings = compose_findings("demo", scan, graph)
    classes = [f["class"] for f in findings]
    assert "load_bearing_change" in classes
    env_gap = next(f for f in findings if f["class"] == "missing_env_var")
    assert env_gap["graph_evidence"]["blast"]["blast_radius"] == 2
    assert env_gap["graph_evidence"]["seen_before"][0]["seen_in"] == "r0"
    hub = next(f for f in findings if f["class"] == "load_bearing_change")
    assert hub["file_path"] == "core.py"
    assert "5 file(s)" in hub["detail"]


def test_to_graph_records_shape():
    findings = [
        {"class": "missing_env_var", "detail": "d", "severity": "error", "file_path": "payments.py"},
        {"class": "model_review", "detail": "d2", "severity": "warning", "file_path": None},
    ]
    records = to_graph_records("r1", "demo", findings)
    assert records[0]["id"] == "r1#0"
    assert records[0]["file_key"] == "demo#payments.py"
    assert records[1]["file_key"] is None


def test_judge_parse_tolerates_garbage():
    assert _parse("not json") == []
    assert _parse('{"findings": "nope"}') == []
    good = '{"findings": [{"class": "silent_failure", "detail": "no retry", "file_path": "n.py", "line": 3, "confidence": 0.7}]}'
    parsed = _parse(f"```json\n{good}\n```")
    assert len(parsed) == 1
    assert parsed[0]["confidence"] == 0.7
    assert parsed[0]["graph_evidence"] == {"query": "nebius_judge"}
    # missing confidence defaults, bad line dropped
    sloppy = '{"findings": [{"class": "x", "detail": "d", "line": "nine"}]}'
    assert _parse(sloppy)[0]["confidence"] == 0.5
    assert _parse(sloppy)[0]["line"] is None
