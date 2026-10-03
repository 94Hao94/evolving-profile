import { NextRequest, NextResponse } from "next/server";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { homedir } from "node:os";

const HOOK_RECEIPTS_PATH = process.env.EVOLVING_PROFILE_HOOK_RECEIPTS_PATH || path.join(homedir(), ".evolving-profile/audit/hook-output-receipts/production");
const PROMPT_INGRESS_PATH = process.env.EVOLVING_PROFILE_PROMPT_INGRESS_PATH || path.join(homedir(), ".evolving-profile/audit/prompt-ingress.jsonl");

async function localPromptDetail(promptId: string) {
  const fingerprint = promptId.split(":", 1)[0];
  try {
    const ingress = (await readFile(PROMPT_INGRESS_PATH, "utf8")).trim().split("\n").reverse().map((line) => JSON.parse(line)).find((row) => row.prompt_fingerprint === fingerprint);
    if (!ingress?.turn_id) return null;
    const files = await readdir(HOOK_RECEIPTS_PATH);
    const hooks = await Promise.all(files.filter((file) => file.endsWith(".json")).map(async (file) => { try { return JSON.parse(await readFile(path.join(HOOK_RECEIPTS_PATH, file), "utf8")); } catch { return null; } }));
    const hook = hooks.find((row: any) => row?.turn_id === ingress.turn_id);
    if (!hook) return null;
    const injected = Array.isArray(hook.injected_items) ? hook.injected_items : [];
    const agentProcess = hook.entry_guidance?.agent_process_memory ?? null;
    return {
      schema: "evolving-profile.guidance-prompt-local-fallback.v1",
      prompt_id: promptId,
      session_id: ingress.session_id,
      turn_id: ingress.turn_id,
      user_prompt: ingress.prompt_preview ?? "",
      guidance_receipt: { host_state: hook.injected_count ? "observed" : "verified_empty", coverage: "prompt_bound_hook_receipt", preference_candidate_count: injected.length, guidance_count: injected.length, guidance_items: injected, deferred_count: 0 },
      historical_audit: { route: "not_observed", state: "not_observed", candidate_count: 0, returned_to_host_count: 0, delivery_state: "verified_empty", items: [] },
      hook_receipts: agentProcess ? [{ at: hook.at, agent_process_memory: agentProcess }] : [],
    };
  } catch { return null; }
}

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ promptId: string }> }
) {
  const { promptId } = await context.params;
  const statusUrl = process.env.EVOLVING_PROFILE_STATUS_API_URL || "http://127.0.0.1:9998";
  const upstream = new URL(`/api/guidance/prompts/${encodeURIComponent(promptId)}`, statusUrl);
  request.nextUrl.searchParams.forEach((value, key) => upstream.searchParams.append(key, value));
  let response: Response;
  try { response = await fetch(upstream, { cache: "no-store", signal: AbortSignal.timeout(3000) }); }
  catch { const fallback = await localPromptDetail(promptId); return fallback ? NextResponse.json(fallback) : NextResponse.json({ error: "guidance_unavailable" }, { status: 503 }); }
  if (!response.ok) { const fallback = await localPromptDetail(promptId); return fallback ? NextResponse.json(fallback) : new NextResponse(await response.text(), { status: response.status, headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" } }); }
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
