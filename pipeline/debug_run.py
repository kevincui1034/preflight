"""Instrumented review run — streams every engine event so we can see
what the agent is actually doing (or failing on)."""

import asyncio
import json
import sys

from rocketride import RocketRideClient


async def handle_events(event):
    kind = event.get("event", "?")
    body = event.get("body", {})
    if kind == "apaevt_task":
        print(f"[task] {body}", flush=True)
    elif isinstance(body, dict) and body.get("message"):
        print(f"[{kind}] {str(body.get('message'))[:300]}", flush=True)
    else:
        print(f"[{kind}] {str(body)[:300]}", flush=True)


async def main():
    review_id = sys.argv[1] if len(sys.argv) > 1 else "debug-test"
    client = RocketRideClient(on_event=handle_events)
    await client.connect()
    result = await client.use(filepath="preflight.pipe")
    token = result["token"]
    print("token:", token, flush=True)
    try:
        await client.monitor(token, types=["TASK", "SUMMARY", "OUTPUT", "DETAIL"])
    except Exception as exc:
        print("monitor subscribe failed (continuing):", exc, flush=True)
    await client.send(
        token,
        json.dumps({
            "review_id": review_id,
            "project_id": "demo",
            "repo_url": "https://github.com/kevincui1034/preflight-demo-service",
            "kind": "free",
        }),
    )
    print("sent — streaming events for 4 minutes", flush=True)
    await asyncio.sleep(240)
    await client.disconnect()


asyncio.run(main())
