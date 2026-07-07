"""Drive preflight.pipe on the connected RocketRide runtime (local or cloud).

    python run_pipe.py [review_id] [repo_url] [kind]

Registers the pipeline, sends one review request through the webhook
source, and polls task status. The agent inside the pipeline does the
work and POSTs findings to the Butterbase callback itself — this driver
only injects the request.
"""

import asyncio
import json
import sys

from rocketride import RocketRideClient


async def main() -> None:
    review_id = sys.argv[1] if len(sys.argv) > 1 else "local-test"
    repo_url = sys.argv[2] if len(sys.argv) > 2 else "https://github.com/preflight-demo/demo-service"
    kind = sys.argv[3] if len(sys.argv) > 3 else "free"
    client = RocketRideClient()
    await client.connect()
    print("connected")
    try:
        result = await client.use(filepath="preflight.pipe")
        token = result["token"]
        print("pipeline token:", token)
        await client.send(
            token,
            json.dumps(
                {"review_id": review_id, "project_id": "demo", "repo_url": repo_url, "kind": kind}
            ),
        )
        print("review request sent — agent is working")
        for _ in range(60):
            await asyncio.sleep(5)
            status = await client.get_task_status(token)
            print("state:", status.get("state"))
            if str(status.get("state", "")).lower() in ("done", "completed", "failed", "error", "idle"):
                break
    finally:
        await client.disconnect()
        print("disconnected")


if __name__ == "__main__":
    asyncio.run(main())
