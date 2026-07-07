// review-callback — service-only (the RocketRide pipeline posts findings
// back with the app-scoped bb_sk key; end-user JWTs are rejected).

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function handler(req: Request, ctx: any): Promise<Response> {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  if (ctx.user) return json({ error: "service key required" }, 403);
  const body = await req.json().catch(() => null);
  if (!body || !body.review_id) return json({ error: "review_id required" }, 400);

  const review = await ctx.db.query(
    "SELECT id, user_id FROM reviews WHERE id = $1",
    [body.review_id],
  );
  if (!review.rows.length) return json({ error: "review not found" }, 404);
  const userId = review.rows[0].user_id;

  const findings = Array.isArray(body.findings) ? body.findings : [];
  for (const f of findings) {
    await ctx.db.query(
      "INSERT INTO findings (review_id, user_id, class, severity, confidence, detail, file_path, line, graph_evidence, model_id) " +
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)",
      [
        body.review_id,
        userId,
        String(f.class || "finding"),
        String(f.severity || "warning"),
        typeof f.confidence === "number" ? f.confidence : null,
        String(f.detail || ""),
        typeof f.file_path === "string" ? f.file_path : null,
        typeof f.line === "number" ? f.line : null,
        JSON.stringify(f.graph_evidence ?? {}),
        f.model_id ?? body.model_id ?? null,
      ],
    );
  }
  await ctx.db.query(
    "UPDATE reviews SET status = $1, model_id = COALESCE($2, model_id), " +
      "blast_radius = COALESCE($3, blast_radius), completed_at = now() WHERE id = $4",
    [
      body.status || "complete",
      body.model_id ?? null,
      typeof body.blast_radius === "number" ? body.blast_radius : null,
      body.review_id,
    ],
  );
  return json({ ok: true, findings: findings.length });
}

export default handler;
