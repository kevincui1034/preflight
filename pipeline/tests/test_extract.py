from pathlib import Path

from preflight_pipeline.extract import scan_repo

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "demo-service"


def _scan():
    return scan_repo(FIXTURE)


def test_files_and_changed_manifest():
    scan = _scan()
    assert "core.py" in scan["files"]
    assert "payments.py" in scan["files"]
    assert scan["changed"] == ["payments.py", "core.py"]


def test_import_edges_make_core_a_hub():
    scan = _scan()
    edges = {(i["src"], i["dst"]) for i in scan["imports"]}
    assert ("payments.py", "core.py") in edges
    assert ("app.py", "core.py") in edges
    fan_in = sum(1 for _, dst in edges if dst == "core.py")
    assert fan_in >= 4, "core.py must be load-bearing in the fixture"


def test_env_reads_with_lines():
    scan = _scan()
    reads = {(r["file"], r["name"]) for r in scan["env_reads"]}
    assert ("payments.py", "STRIPE_API_KEY") in reads
    assert ("db.py", "DATABASE_URL") in reads
    assert all(r["line"] > 0 for r in scan["env_reads"])


def test_prod_manifest_parsed():
    scan = _scan()
    assert scan["prod_manifest"] == "deploy/prod.env"
    assert "DATABASE_URL" in scan["prod_env"]
    assert "STRIPE_API_KEY" not in scan["prod_env"]


def test_secret_scan_hits_notifications_only():
    scan = _scan()
    files = {s["file"] for s in scan["secrets"]}
    assert files == {"notifications.py"}


def test_env_read_detection_variants(tmp_path):
    (tmp_path / "m.py").write_text(
        "import os\n"
        "from os import environ, getenv\n"
        'a = os.environ["A"]\n'
        'b = os.environ.get("B", "x")\n'
        'c = os.getenv("C")\n'
        'd = environ["D"]\n'
        'e = getenv("E")\n'
    )
    scan = scan_repo(tmp_path)
    names = {r["name"] for r in scan["env_reads"]}
    assert names == {"A", "B", "C", "D", "E"}
