import { NextRequest, NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { homedir } from "node:os";

const RESOURCES = new Set(["units", "models", "candidates", "prompts", "memory-map", "memory-check"]);
const PROMPT_INGRESS_PATH = process.env.EVOLVING_PROFILE_PROMPT_INGRESS_PATH || path.join(homedir(), ".evolving-profile/audit/prompt-ingress.jsonl");

async function localPromptList(request: NextRequest) {
  const limit = Math.min(Number(request.nextUrl.searchParams.get("limit") || 20), 50);
  const cursor = Math.max(Number(request.nextUrl.searchParams.get("cursor") || 0), 0);
  const host = request.nextUrl.searchParams.get("host") || "all";
  const query = (request.nextUrl.searchParams.get("q") || "").trim().toLowerCase();
  try {
    const rows = (await readFile(PROMPT_INGRESS_PATH, "utf8")).trim().split("\n").map((line) => JSON.parse(line)).reverse().filter((row: any) => (host === "all" || String(row.host_id || "").toLowerCase() === host.toLowerCase()) && (!query || String(row.prompt_preview || "").toLowerCase().includes(query)));
    const items = rows.slice(cursor, cursor + limit).map((row: any) => ({ prompt_id: `${row.prompt_fingerprint}:${row.at}`, at: row.at, user_prompt: row.prompt_preview || "", source: row.host_id || "codex", routes: {}, candidate_groups: [], local_fallback: true }));
    return NextResponse.json({ schema: "evolving-profile.guidance-prompts-local-fallback.v1", items, has_more: cursor + limit < rows.length, cursor, source_scope: "local_prompt_ingress_fallback" });
  } catch { return null; }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ resource: string }> }
) {
  const { resource } = await context.params;
  if (!RESOURCES.has(resource)) {
    return NextResponse.json({ error: "Unknown Evolving Profile guidance resource" }, { status: 404 });
  }

  const statusUrl = process.env.EVOLVING_PROFILE_STATUS_API_URL || "http://127.0.0.1:9998";
  const upstream = new URL(`/api/guidance/${resource}`, statusUrl);
  request.nextUrl.searchParams.forEach((value, key) => upstream.searchParams.append(key, value));
  let response: Response;
  try { response = await fetch(upstream, { cache: "no-store", signal: AbortSignal.timeout(3000) }); }
  catch { return resource === "prompts" ? (await localPromptList(request)) ?? NextResponse.json({ error: "guidance_unavailable" }, { status: 503 }) : NextResponse.json({ error: "guidance_unavailable" }, { status: 503 }); }
  if (!response.ok && resource === "prompts") return (await localPromptList(request)) ?? new NextResponse(await response.text(), { status: response.status, headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" } });
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
