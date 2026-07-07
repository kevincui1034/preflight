"""Repo extraction — everything the graph is built from.

Pure filesystem + ast; no network, no Neo4j. Python-only today (the
fixture and most agent-built services); other languages are a post-
hackathon concern.
"""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

EXCLUDED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist"}

#: Files that declare what production actually sets (first hit wins).
PROD_ENV_MANIFESTS = ("deploy/prod.env", "prod.env", ".env.production", ".env.prod")

#: Explicit change manifest for demo/fixture repos without git history.
CHANGED_MANIFEST = ".preflight-changed"

#: Hardcoded-credential shapes (token prefixes + generic assignment).
SECRET_PATTERNS = [
    re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{8,}"),
    re.compile(r"whsec_[A-Za-z0-9]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"xox[bap]-[A-Za-z0-9-]{10,}"),
    re.compile(
        r"""(?ix)(secret|token|api_?key|password)\s*=\s*["'][^"']{16,}["']"""
    ),
]


def _python_files(root: Path) -> list[Path]:
    out = []
    for path in sorted(root.rglob("*.py")):
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDED_DIRS:
            continue
        out.append(path)
    return out


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root))


def _resolve_import(module: str, root: Path) -> str | None:
    """Map a module name to a repo-relative file, if it lives in the repo."""
    base = module.split(".")
    candidates = [
        root.joinpath(*base).with_suffix(".py"),
        root.joinpath(*base, "__init__.py"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return _rel(candidate, root)
    return None


def _imports_of(tree: ast.AST, root: Path) -> set[str]:
    targets: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve_import(alias.name, root)
                if resolved:
                    targets.add(resolved)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            resolved = _resolve_import(node.module, root)
            if resolved:
                targets.add(resolved)
    return targets


def _env_reads_of(tree: ast.AST) -> list[tuple[str, int]]:
    """(env var name, line) for os.environ[...] / .get(...) / os.getenv(...)."""
    reads: list[tuple[str, int]] = []

    def _is_environ(node: ast.AST) -> bool:
        return (isinstance(node, ast.Attribute) and node.attr == "environ") or (
            isinstance(node, ast.Name) and node.id == "environ"
        )

    def _const_str(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _is_environ(node.value):
            name = _const_str(node.slice)
            if name:
                reads.append((name, node.lineno))
        elif isinstance(node, ast.Call):
            func = node.func
            is_environ_get = (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and _is_environ(func.value)
            )
            is_getenv = (
                isinstance(func, ast.Attribute) and func.attr == "getenv"
            ) or (isinstance(func, ast.Name) and func.id == "getenv")
            if (is_environ_get or is_getenv) and node.args:
                name = _const_str(node.args[0])
                if name:
                    reads.append((name, node.lineno))
    return reads


def _scan_secrets(path: Path, root: Path) -> list[dict]:
    hits: list[dict] = []
    rel = _rel(path, root)
    if "test" in rel:
        return hits
    for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                hits.append({"file": rel, "line": lineno, "match": pattern.pattern})
                break  # one hit per line
    return hits


def _prod_env_names(root: Path) -> tuple[list[str], str | None]:
    for manifest in PROD_ENV_MANIFESTS:
        path = root / manifest
        if path.is_file():
            names = []
            for line in path.read_text(errors="replace").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    names.append(line.split("=", 1)[0].strip())
            return names, manifest
    return [], None


def _changed_files(root: Path, all_files: list[str]) -> list[str]:
    """Changed set: .preflight-changed manifest → git last commit → all."""
    manifest = root / CHANGED_MANIFEST
    if manifest.is_file():
        names = [l.strip() for l in manifest.read_text().splitlines() if l.strip()]
        return [n for n in names if n in all_files]
    try:
        cp = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1"],
            cwd=root, capture_output=True, text=True, timeout=10,
        )
        if cp.returncode == 0:
            names = [l.strip() for l in cp.stdout.splitlines() if l.strip()]
            changed = [n for n in names if n in all_files]
            if changed:
                return changed
    except Exception:
        pass
    return list(all_files)


def scan_repo(root: Path) -> dict:
    """One JSON-able scan of the repo — the input to every later stage."""
    root = Path(root).resolve()
    files: list[str] = []
    imports: list[dict] = []
    env_reads: list[dict] = []
    secrets: list[dict] = []
    for path in _python_files(root):
        rel = _rel(path, root)
        files.append(rel)
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        for target in sorted(_imports_of(tree, root)):
            if target != rel:
                imports.append({"src": rel, "dst": target})
        for name, line in _env_reads_of(tree):
            env_reads.append({"file": rel, "line": line, "name": name})
        secrets.extend(_scan_secrets(path, root))
    prod_env, prod_manifest = _prod_env_names(root)
    return {
        "files": files,
        "imports": imports,
        "env_reads": env_reads,
        "secrets": secrets,
        "prod_env": prod_env,
        "prod_manifest": prod_manifest,
        "changed": _changed_files(root, files),
    }
