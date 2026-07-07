// claim-credits — user-facing. After Stripe Checkout completes, the
// success page calls this: it reads the user's paid orders from the
// platform billing API and credits the ledger exactly once per order
// (ctx.idempotency.claim guards against replays/retries).

const API_BASE = "https://api.butterbase.ai";

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function handler(req: Request, ctx: any): Promise<Response> {
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  if (!ctx.user) return json({ error: "sign in required" }, 401);
  const auth = req.headers.get("Authorization") || "";
  const appId = ctx.env.APP_ID;

  const resp = await fetch(`${API_BASE}/v1/${appId}/billing/orders`, {
    headers: { Authorization: auth },
  });
  if (!resp.ok) return json({ error: "orders unavailable", status: resp.status }, 502);
  const payload = await resp.json();
  const orders = Array.isArray(payload) ? payload : payload.orders || [];

  let credited = 0;
  for (const order of orders) {
    if (order.status !== "paid") continue;
    const claimed = await ctx.idempotency.claim(String(order.id), { scope: "credits" });
    if (!claimed) continue;
    const credits = Number(order.metadata?.credits ?? ctx.env.CREDITS_PER_PACK ?? 5);
    await ctx.db.query(
      "INSERT INTO credits_ledger (user_id, delta, reason) VALUES ($1, $2, $3)",
      [ctx.user.id, credits, "purchase:" + order.id],
    );
    credited += credits;
  }
  const bal = await ctx.db.query(
    "SELECT COALESCE(SUM(delta), 0) AS balance FROM credits_ledger WHERE user_id = $1",
    [ctx.user.id],
  );
  return json({ credited, balance: Number(bal.rows[0].balance) });
}

export default handler;
