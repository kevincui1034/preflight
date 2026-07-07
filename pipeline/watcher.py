"""Demo watcher — runs any queued review for the demo account every 10s.

Stands in for the RocketRide dispatch during the demo window: polls the
reviews table (demo user's JWT, RLS-scoped), joins the project repo_url,
and pushes each queued review through the working pipeline stages.
"""

import json
import time
import urllib.request

from service import review as run_review

API = "https://api.butterbase.ai"
APP = "app_pwpiaegbqw20"


def call(path, method="GET", body=None, token=None):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": "Bearer " + token} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def token():
    return call(f"/auth/{APP}/login", "POST",
                {"email": "demo@preflight.dev", "password": "Preflight1!"})["access_token"]


def main():
    tok, tok_at = token(), time.time()
    print("watcher up", flush=True)
    while True:
        try:
            if time.time() - tok_at > 2400:
                tok, tok_at = token(), time.time()
            reviews = call(f"/v1/{APP}/reviews", token=tok)
            projects = {p["id"]: p for p in call(f"/v1/{APP}/projects", token=tok)}
            for r in reviews:
                if r["status"] != "queued":
                    continue
                repo = projects.get(r["project_id"], {}).get("repo_url")
                if not repo:
                    continue
                print("running", r["id"][:8], r["kind"], repo, flush=True)
                out = run_review({
                    "review_id": r["id"],
                    "project_id": r["project_id"][:8],
                    "repo_url": repo,
                    "kind": r["kind"],
                })
                print("done", r["id"][:8], out, flush=True)
        except Exception as exc:
            print("watcher error:", str(exc)[:120], flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
