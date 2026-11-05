// Cloudflare Pages Function: POST /api/feedback -> private GitHub issue.
// Sits behind Cloudflare Access with the rest of the site, so only allowed emails can reach it.
// Needs a Pages secret GITHUB_TOKEN (fine-grained token, Issues: read & write on the repo only).

const REPO = "rcxkz/verisure-kraig";
const TYPES = new Set(["Bug", "Idea", "Wrong data"]);

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json" } });

export async function onRequestPost({ request, env }) {
  let body;
  try { body = await request.json(); } catch { return json({ ok: false, error: "bad json" }, 400); }
  const message = String(body?.message || "").trim().slice(0, 4000);
  if (!message) return json({ ok: false, error: "empty" }, 400);
  if (!env.GITHUB_TOKEN) return json({ ok: false, error: "feedback not configured" }, 503);

  const type = TYPES.has(body.type) ? body.type : "Bug";
  const who = request.headers.get("Cf-Access-Authenticated-User-Email") || "unknown";
  const firstLine = message.split("\n")[0].slice(0, 70);
  const issue = {
    title: `[${type}] ${firstLine}`,
    body: [
      message,
      "",
      "---",
      `- From: ${who}`,
      `- Page: ${String(body.page || "").slice(0, 40)}`,
      `- Data version: ${String(body.generated || "").slice(0, 40)}`,
      `- Sent: ${String(body.at || new Date().toISOString()).slice(0, 40)}`,
      `- Device: ${(request.headers.get("User-Agent") || "").slice(0, 200)}`,
    ].join("\n"),
  };

  const r = await fetch(`https://api.github.com/repos/${REPO}/issues`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GITHUB_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "door-leads-feedback",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify(issue),
  });
  if (!r.ok) return json({ ok: false, error: `github ${r.status}` }, 502);
  const created = await r.json();
  return json({ ok: true, number: created.number });
}

export const onRequest = () => json({ ok: false, error: "POST only" }, 405);
