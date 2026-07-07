// create-review — user-facing (requires end-user JWT; RLS enforced).
// Creates/finds the project, charges a credit for deep reviews, inserts
// the review row, and dispatches the RocketRide cloud pipeline.

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function handler(req: Request, ctx: any): Promise<Response> {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  if (!ctx.user) return json({ error: "sign in required" }, 401);
  const body = await req.json().catch(() => ({}));
  const kind = body.kind === "deep" ? "deep" : "free";
  const repoUrl = typeof body.repo_url === "string" ? body.repo_url : null;

  let projectId = body.project_id ?? null;
  if (!projectId) {
    if (!repoUrl) return json({ error: "repo_url or project_id required" }, 400);
    const existing = await ctx.db.query(
      "SELECT id FROM projects WHERE repo_url = $1 LIMIT 1",
      [repoUrl],
    );
    if (existing.rows.length) {
      projectId = existing.rows[0].id;
    } else {
      const name = body.name || repoUrl.split("/").filter(Boolean).pop() || "project";
      const inserted = await ctx.db.query(
        "INSERT INTO projects (user_id, name, repo_url) VALUES ($1, $2, $3) RETURNING id",
        [ctx.user.id, name, repoUrl],
      );
      projectId = inserted.rows[0].id;
    }
  }

  if (kind === "deep") {
    const bal = await ctx.db.query(
      "SELECT COALESCE(SUM(delta), 0) AS balance FROM credits_ledger WHERE user_id = $1",
      [ctx.user.id],
    );
    if (Number(bal.rows[0].balance) < 1) {
      return json(
        { error: "insufficient_credits", balance: Number(bal.rows[0].balance) },
        402,
      );
    }
  }

  const review = await ctx.db.query(
    "INSERT INTO reviews (project_id, user_id, kind, status) VALUES ($1, $2, $3, 'queued') RETURNING id",
    [projectId, ctx.user.id, kind],
  );
  const reviewId = review.rows[0].id;
  if (kind === "deep") {
    await ctx.db.query(
      "INSERT INTO credits_ledger (user_id, delta, reason, review_id) VALUES ($1, -1, 'deep_review', $2)",
      [ctx.user.id, reviewId],
    );
  }

  // Dispatch the managed pipeline on cloud.rocketride.ai. Unset endpoint
  // (pre-deploy) leaves the review 'queued' so the dashboard shows it.
  let dispatched = false;
  const endpoint = ctx.env.ROCKETRIDE_ENDPOINT;
  if (endpoint) {
    try {
      const resp = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(ctx.env.ROCKETRIDE_TOKEN
            ? { Authorization: `Bearer ${ctx.env.ROCKETRIDE_TOKEN}` }
            : {}),
        },
        body: JSON.stringify({
          review_id: reviewId,
          project_id: projectId,
          repo_url: repoUrl,
          kind,
        }),
      });
      dispatched = resp.ok;
      await ctx.db.query("UPDATE reviews SET status = $1 WHERE id = $2", [
        resp.ok ? "running" : "failed",
        reviewId,
      ]);
    } catch (_err) {
      await ctx.db.query("UPDATE reviews SET status = 'failed' WHERE id = $1", [
        reviewId,
      ]);
    }
  }
  return json({ review_id: reviewId, project_id: projectId, kind, dispatched });
}

export default handler;
