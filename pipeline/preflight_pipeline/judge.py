"""Deep-review judge on Nebius (OpenAI-compatible chat/completions).

Model judgment rides ON TOP of the deterministic findings — it never
removes or overrides them. Best-effort: any error or timeout returns no
extra findings, so a review never fails because the judge did.
"""

from __future__ import annotations

import json
import os
import re

import httpx

DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
DEFAULT_MODEL = "meta-llama/Llama-3.3-70B-Instruct"
TIMEOUT_SECONDS = 30.0

SYSTEM_PROMPT = (
    "You are Preflight's deploy-readiness reviewer. You receive a repo scan "
    "(imports, env reads, changed files), graph traversal results (blast "
    "radius, load-bearing files, prod env gaps, past failures), and the "
    "deterministic findings already raised. Add ONLY genuinely new risks "
    "visible in the data — silent failure modes, missing error handling, "
    "risky changes to load-bearing files. Do not repeat findings already "
    'listed. Respond as strict JSON: {"findings": [{"class": "<slug>", '
    '"detail": "<1-2 sentences>", "file_path": "<path>"|null, "line": '
    '<int>|null, "confidence": <0.0-1.0>}]}. An empty list is a good answer.'
)

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _parse(content: str) -> list[dict]:
    try:
        parsed = json.loads(_FENCE_RE.sub("", content.strip()).strip())
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, dict) or not isinstance(parsed.get("findings"), list):
        return []
    out = []
    for item in parsed["findings"]:
        if not isinstance(item, dict):
            continue
        detail = item.get("detail")
        if not isinstance(detail, str) or not detail.strip():
            continue
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            confidence = 0.5
        line = item.get("line")
        out.append(
            {
                "class": str(item.get("class") or "model_review"),
                "severity": "warning",
                "confidence": min(1.0, max(0.0, float(confidence))),
                "detail": " ".join(detail.split()),
                "file_path": item.get("file_path") if isinstance(item.get("file_path"), str) else None,
                "line": line if isinstance(line, int) and not isinstance(line, bool) else None,
                "graph_evidence": {"query": "nebius_judge"},
            }
        )
    return out


def judge_review(scan: dict, graph: dict | None, findings: list[dict]) -> tuple[list[dict], str | None]:
    """(extra findings, model_id). ([], None) when unconfigured or on error."""
    api_key = os.environ.get("NEBIUS_API_KEY")
    if not api_key:
        return [], None
    base_url = (os.environ.get("NEBIUS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
    model = os.environ.get("NEBIUS_MODEL") or DEFAULT_MODEL
    user_payload = json.dumps(
        {
            "changed": scan["changed"],
            "env_reads": scan["env_reads"],
            "imports": scan["imports"],
            "graph": graph or {},
            "existing_findings": [
                {"class": f["class"], "detail": f["detail"]} for f in findings
            ],
        },
        ensure_ascii=False,
    )
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_payload},
                    ],
                    "max_tokens": 800,
                },
            )
            response.raise_for_status()
            data = response.json()
        content = data["choices"][0]["message"]["content"]
        model_id = data.get("model") or model
        extras = _parse(content)
        for extra in extras:
            extra["model_id"] = model_id
        return extras, model_id
    except Exception:
        return [], None
