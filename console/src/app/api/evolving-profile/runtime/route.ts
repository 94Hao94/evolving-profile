import { NextResponse } from "next/server";
import { readdir, readFile, stat } from "node:fs/promises";
import { promisify } from "node:util";
import { execFile } from "node:child_process";
import path from "node:path";
import { homedir } from "node:os";
import { parseCloudReadbackReceipt, summarizeCloudBackups, summarizeLocalBackups, type BackupFile, type CloudBackupSet } from "@/lib/backup-status";
import { isScenarioBankScope, summarizeAssociationCoverage, summarizeScenarioStatus } from "@/lib/scenario-status";
import { projectSessionContextNode } from "@/lib/context-node";
import { resolveConsoleOrigin } from "@/lib/console-origin";

const STATE_ROOT = process.env.EVOLVING_PROFILE_STATE_ROOT ?? path.join(process.env.HOME ?? homedir(), ".evolving-profile");
const ENV_PATH = path.join(STATE_ROOT, "profiles/evolving-profile-api.env");
const PROFILE_PATH = path.join(STATE_ROOT, "codex.json");
const LOCAL_BACKUP_PATH = path.join(STATE_ROOT, "backups/managed/daily");
const WPS_CACHE_PATH = process.env.EVOLVING_PROFILE_WPS_CACHE_PATH ?? path.join(STATE_ROOT, "backups/cloud-mirror");
const WPS_CLOUD_RECEIPT_PATH = path.join(STATE_ROOT, "runtime/wps-cloud-upload-receipt.json");
const CLOUD_MIRROR_PATH = WPS_CACHE_PATH;
const BACKUP_SETTINGS_PATH = path.join(STATE_ROOT, "config/backup-settings.json");
const GUIDANCE_SETTINGS_PATH = path.join(STATE_ROOT, "config/guidance-settings.json");
const RUNTIME_SETTINGS_PATH = path.join(STATE_ROOT, "config/runtime-settings.json");
const CONTEXT_INDEX_PATH = path.join(STATE_ROOT, "context/context-index.json");
const CONTEXT_PROGRESS_PATH = path.join(STATE_ROOT, "context/context-pipeline-progress.json");
const CONTEXT_AUDIT_PATH = path.join(STATE_ROOT, "context/context-audit.json");
const CONTEXT_BANK_ASSOCIATIONS_PATH = path.join(STATE_ROOT, "context/context-bank-associations.json");
const RELEASE_MANIFEST_PATH = path.join(STATE_ROOT, "config/release-manifest.json");
const PERSONAL_BANK_ID = "personal-memory";
const RUNTIME_SETTINGS_DEFAULTS = {
  schema: "evolving-profile.runtime-settings.v1",
  modules: Object.fromEntries(["facts", "experiences", "entities", "preferences", "scenario_summary", "mental_models", "source_readback", "background_reflection"].map((name) => [name, { record: true, retrieve: true, inject: true }])),
  routing: { mode: "auto", ep_enabled: true, external_rag_enabled: false, allow_parallel: false, conflict_policy: "show_both" },
  budgets: { ep_total_tokens: 4000, rag_total_tokens: 4000, total_tokens: 6000, preference_tokens: 1200, scenario_tokens: 1200, source_tokens: 2400 },
  rag: { enabled: false, root_path: "", collection: "default", lexical_enabled: true, vector_enabled: true, fusion: "rrf", lexical_weight: 0.5, vector_weight: 0.5, rerank_enabled: true, rerank_provider: "local", rerank_model: "", top_k: 20, score_threshold: 0.35, max_chunks: 8, auto_index: false },
  retrieval_models: { embedding: { enabled: true, mode: "local", provider: "onnx", model: "intfloat/multilingual-e5-small", local_path: "", dimensions: 384, max_tokens: 512, device: "cpu", profile_id: "embedding-default", status: "configured" }, reranker: { enabled: true, mode: "local", provider: "local", model: "BAAI/bge-reranker-base", local_path: "", device: "cpu", profile_id: "reranker-default", status: "configured" }, embedding_profiles: [], reranker_profiles: [], fusion: { enabled: true, algorithm: "rrf", profile_id: "fusion-rrf" }, judge: { enabled: false, provider: "jev", mode: "api", base_url: "", model: "", api_key: "", timeout_ms: 5000, max_tokens: 600, mode_policy: "off", fallback: "rules", send_scope: "metadata_summary", risk_gate_enabled: false, status: "disabled" } },
  providers: { primary: { name: "", base_url: "", model: "", api_key: null }, fallbacks: [] },
};
const execFileAsync = promisify(execFile);

function mergeSettings(base: any, value: any): any {
  if (!value || typeof value !== "object" || Array.isArray(value)) return base;
  const result = { ...base };
  for (const [key, item] of Object.entries(value)) result[key] = item && typeof item === "object" && !Array.isArray(item) && base[key] && typeof base[key] === "object" ? mergeSettings(base[key], item) : item;
  return result;
}

function parseEnv(source: string): Record<string, string> {
  return Object.fromEntries(
    source
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith("#") && line.includes("="))
      .map((line) => {
        const index = line.indexOf("=");
        return [line.slice(0, index), line.slice(index + 1)];
      })
  );
}

function maskSecret(value: string | undefined): string | null {
  if (!value) return null;
  return value.length <= 4 ? "••••" : `••••${value.slice(-4)}`;
}

async function serviceState(url: string) {
  try {
    const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(1200) });
    const body = await response.json().catch(() => ({}));
    return { url, status: response.ok ? "healthy" : "attention", detail: body.functional_status ?? body.status ?? response.status };
  } catch {
    return { url, status: "unavailable", detail: "unreachable" };
  }
}

async function liveBankRecordTotal(): Promise<number | null> {
  try {
    const response = await fetch(`http://127.0.0.1:12088/v1/default/banks/${PERSONAL_BANK_ID}/memories/list?limit=0`, {
      cache: "no-store", signal: AbortSignal.timeout(1500),
    });
    if (!response.ok) return null;
    const total = Number((await response.json()).total);
    return Number.isFinite(total) ? total : null;
  } catch { return null; }
}

async function flatFiles(root: string): Promise<BackupFile[]> {
  try {
    const entries = await readdir(root, { withFileTypes: true });
    return await Promise.all(entries.filter((entry) => entry.isFile()).map(async (entry) => {
      const info = await stat(path.join(root, entry.name));
      return { name: entry.name, bytes: info.size, modifiedMs: info.mtimeMs };
    }));
  } catch { return []; }
}

async function wpsCloudReadback() {
  try {
    return parseCloudReadbackReceipt(JSON.parse(await readFile(WPS_CLOUD_RECEIPT_PATH, "utf8")));
  } catch { return { observed: false }; }
}

async function backupJobState() {
  try {
    const { stdout } = await execFileAsync("launchctl", ["print", `gui/${process.getuid?.() ?? 501}/com.evolving-profile.backup`], { timeout: 1500 });
    return {
      loaded: true,
      running: stdout.includes("state = running"),
      lastExitCode: Number(stdout.match(/last exit code = (\d+)/)?.[1] ?? 0),
      schedule: "每日 03:25",
    };
  } catch { return { loaded: false, running: false, lastExitCode: null, schedule: "每日 03:25" }; }
}

function scheduleLabel(settings: Record<string, any>) {
  const schedule = settings.schedule ?? {};
  const time = `${String(schedule.hour ?? 3).padStart(2, "0")}:${String(schedule.minute ?? 25).padStart(2, "0")}`;
  if (schedule.mode === "weekly") return `每周${["日", "一", "二", "三", "四", "五", "六"][schedule.weekday ?? 1]} ${time}`;
  if (schedule.mode === "monthly") return `每月 ${schedule.day ?? 1} 日 ${time}`;
  return `每日 ${time}`;
}

export async function GET(request?: Request) {
  const requestedBank = request ? new URL(request.url).searchParams.get("bankId") : null;
  const scenarioBankVisible = isScenarioBankScope(requestedBank, PERSONAL_BANK_ID);
  let env: Record<string, string> = {};
  let profile: Record<string, unknown> = {};
  let backupSettings: Record<string, unknown> = {};
  let guidanceSettings: Record<string, unknown> = {};
  let runtimeSettings: Record<string, any> = {};
  let releaseManifest: Record<string, any> = { product_version: "4.0", release_channel: "development" };
  let contextIndex: Record<string, any> = { status: "unavailable", sessions: [], projects: [] };
  let contextProgress: Record<string, any> = { status: "unavailable", total: 0, queued: 0, running: 0, retrying: 0, succeeded: 0, failed: 0 };
  let contextAudit: Record<string, any> = { status: "not_run", error_count: null, warning_count: null };
  let contextAssociations: Record<string, any> = { linked_records: 0, links: [] };
  try {
    env = parseEnv(await readFile(ENV_PATH, "utf8"));
  } catch {
    // The page remains truthful when the operator-managed env file is unavailable.
  }
  try {
    profile = JSON.parse(await readFile(PROFILE_PATH, "utf8"));
  } catch {
    // The page remains truthful when the operator-managed profile is unavailable.
  }
  try { backupSettings = JSON.parse(await readFile(BACKUP_SETTINGS_PATH, "utf8")); } catch { /* defaults are shown by the settings panel */ }
  const guidanceDefaults = { schema: "evolving-profile.guidance-settings.v1", max_candidates: 6, adaptive_budget: true, auto_probe: true, probe_max_tokens: 500 };
  try { guidanceSettings = { ...guidanceDefaults, ...JSON.parse(await readFile(GUIDANCE_SETTINGS_PATH, "utf8")) }; } catch { guidanceSettings = guidanceDefaults; }
  try { runtimeSettings = mergeSettings(RUNTIME_SETTINGS_DEFAULTS, JSON.parse(await readFile(RUNTIME_SETTINGS_PATH, "utf8"))); } catch { runtimeSettings = RUNTIME_SETTINGS_DEFAULTS; }
  try { releaseManifest = JSON.parse(await readFile(RELEASE_MANIFEST_PATH, "utf8")); } catch { /* use safe fallback */ }
  runtimeSettings.retrieval_models.embedding = { ...runtimeSettings.retrieval_models.embedding, provider: env.EVOLVING_PROFILE_API_EMBEDDINGS_PROVIDER || runtimeSettings.retrieval_models.embedding.provider, model: env.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MODEL_ID || runtimeSettings.retrieval_models.embedding.model, dimensions: Number(env.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_DIMENSIONS || runtimeSettings.retrieval_models.embedding.dimensions) };
  runtimeSettings.retrieval_models.reranker = { ...runtimeSettings.retrieval_models.reranker, provider: env.EVOLVING_PROFILE_API_RERANKER_PROVIDER === "rrf" ? "local" : env.EVOLVING_PROFILE_API_RERANKER_PROVIDER || runtimeSettings.retrieval_models.reranker.provider, model: env.EVOLVING_PROFILE_API_RERANKER_LOCAL_MODEL || runtimeSettings.retrieval_models.reranker.model };
  const effectiveProvider = {
    name: String(runtimeSettings.providers?.primary?.name || (env.EVOLVING_PROFILE_API_LLM_BASE_URL?.includes("127.0.0.1:3211") ? "Coding Plan" : env.EVOLVING_PROFILE_API_LLM_PROVIDER || "")),
    base_url: String(runtimeSettings.providers?.primary?.base_url || env.EVOLVING_PROFILE_API_LLM_BASE_URL || ""),
    model: String(runtimeSettings.providers?.primary?.model || env.EVOLVING_PROFILE_API_LLM_MODEL || ""),
    api_key: runtimeSettings.providers?.primary?.api_key || env.EVOLVING_PROFILE_API_LLM_API_KEY || "",
  };
  runtimeSettings = { ...runtimeSettings, providers: { ...(runtimeSettings.providers || {}), primary: effectiveProvider } };
  try { contextIndex = JSON.parse(await readFile(CONTEXT_INDEX_PATH, "utf8")); } catch { /* context remains explicitly unavailable */ }
  try { contextProgress = JSON.parse(await readFile(CONTEXT_PROGRESS_PATH, "utf8")); } catch { /* progress remains unavailable */ }
  try { contextAudit = JSON.parse(await readFile(CONTEXT_AUDIT_PATH, "utf8")); } catch { /* audit remains unavailable */ }
  try { contextAssociations = JSON.parse(await readFile(CONTEXT_BANK_ASSOCIATIONS_PATH, "utf8")); } catch { /* associations remain unavailable */ }

  const [api, controller, localFiles, cloudReadback, backupJob, liveBankTotal] = await Promise.all([
    serviceState("http://127.0.0.1:12088/health"),
    serviceState("http://127.0.0.1:12079/health"),
    flatFiles(LOCAL_BACKUP_PATH), wpsCloudReadback(), backupJobState(), liveBankRecordTotal(),
  ]);
  backupJob.schedule = scheduleLabel(backupSettings);
  const localBackup = summarizeLocalBackups(localFiles);
  const mirrorSets: CloudBackupSet[] = cloudReadback.observed && cloudReadback.fileName ? [{
    setName: cloudReadback.fileName.replace(/\.zip$/i, ""), bytes: cloudReadback.fileSize ?? 0,
    modifiedMs: cloudReadback.completedAt ? Date.parse(cloudReadback.completedAt) : Date.now(), encryptedFiles: 1, plaintextFiles: 0,
  }] : [];
  // Do not touch WPS's placeholder cache on the request path. It can block
  // filesystem workers, and cache presence is not proof of a completed upload.
  const wpsCache = { present: false, fileCount: 0, timedOut: false, probeSkipped: true };
  const cloudBackup = summarizeCloudBackups(mirrorSets, wpsCache, Date.now(), cloudReadback);
  const bankLinks = Array.isArray(contextAssociations.links) ? contextAssociations.links : [];
  const verifiedProjectKeys = new Set((contextIndex.projects ?? []).filter((row: any) => row.identity_status === "verified_project").map((row: any) => row.project_key));
  const scenarioStatus = summarizeScenarioStatus(contextIndex);
  const associationCoverage = summarizeAssociationCoverage(Number(contextAssociations.scanned_records ?? 0), liveBankTotal);
  const bankNodes = bankLinks.slice(0, 500).map((row: any) => ({ id: `bank:${row.record_id}`, type: `bank_${row.record_type}`, label: row.record_id, projectKey: row.project_key, status: "linked" }));
  const bankEdges = bankLinks.slice(0, 500).flatMap((row: any) => [
    ...(row.project_key ? [{ source: `project:${row.project_key}`, target: `bank:${row.record_id}`, type: verifiedProjectKeys.has(row.project_key) ? "project_contains_bank_record" : "workspace_links_bank_record" }] : []),
    ...(row.session_ids ?? []).map((sessionId: string) => ({ source: `session:${sessionId}`, target: `bank:${row.record_id}`, type: "session_supports_bank_record" })),
  ]);
  const contextNodes = [
    ...(Array.isArray(contextIndex.projects) ? contextIndex.projects : []).map((row: any) => ({ id: row.context_id, type: row.identity_status === "verified_project" ? "project" : "workspace", label: row.project_key, identityStatus: row.identity_status ?? "unverified_workspace_bucket", status: row.status, sessionCount: (row.session_ids ?? []).length, summary: row.summary ?? {}, summaryBudget: row.summary_budget ?? {}, sourceIds: row.source_ids ?? [], sessionIds: row.session_ids ?? [] })),
    ...(Array.isArray(contextIndex.sessions) ? contextIndex.sessions : []).map(projectSessionContextNode),
    ...bankNodes,
  ];
  const contextEdges = [
    ...(Array.isArray(contextIndex.projects) ? contextIndex.projects : []).flatMap((row: any) => (row.session_ids ?? []).map((sessionId: string) => ({ source: row.context_id, target: `session:${sessionId}`, type: row.identity_status === "verified_project" ? "project_contains_session" : "workspace_contains_session" }))),
    ...bankEdges,
  ];
  const contextTimeline = [
    [...(contextIndex.projects ?? []), ...(contextIndex.sessions ?? [])].map((row: any) => ({ id: row.context_id, type: row.context_type === "project" && row.identity_status !== "verified_project" ? "workspace" : row.context_type, at: row.updated_at, label: row.context_type === "project" ? row.project_key : row.session_id, status: row.status })),
    ...bankLinks.slice(0, 500).map((row: any) => ({ id: `bank:${row.record_id}`, type: `bank_${row.record_type}`, at: row.at, label: row.record_id, status: "linked" })),
  ].flat().sort((a: any, b: any) => String(a.at ?? "").localeCompare(String(b.at ?? "")));

  return NextResponse.json({
    schema: "evolving-profile.runtime.v1",
    release: releaseManifest,
    model: {
      provider: effectiveProvider.name || env.EVOLVING_PROFILE_API_LLM_PROVIDER || "not_configured",
      model: effectiveProvider.model || env.EVOLVING_PROFILE_API_LLM_MODEL || "not_configured",
      baseUrl: effectiveProvider.base_url || env.EVOLVING_PROFILE_API_LLM_BASE_URL || "not_configured",
      apiKey: maskSecret(effectiveProvider.api_key || env.EVOLVING_PROFILE_API_LLM_API_KEY),
    },
    services: [
      { name: "Evolving Profile API", ...api },
      { name: "Query Controller", ...controller },
      { name: "Recovery Service", url: "http://127.0.0.1:12079", status: controller.status, detail: controller.status === "healthy" ? "Controller recovery lanes + runtime guidance refresh" : "recovery unavailable" },
      { name: "Console", url: resolveConsoleOrigin(request?.url ?? "http://127.0.0.1:9999", process.env.PORT), status: "healthy", detail: "current request origin" },
    ],
    hostIntegration: {
      hosts: ["Codex", "Claude Code", "Hermes"],
      hookStages: ["SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact", "Stop"],
      mcpServer: "evolving-profile-controller-mcp",
      entry: "get_preference",
    },
    behavior: {
      guidance: "入口指导检查只选择已有多维度偏好与融合心智模型，不创建长期模型。",
      retrieval: profile.autoRecall === false
        ? "入口可执行独立的一次有界候选探测；单点问题主动 Recall，综合盘点可直接 Research，关键结论读取 read_source 的原文。探测候选不代表问题已覆盖。"
        : "自动历史召回仍开启；Codex 也可按需使用 recall、research 与 read_source。",
      controller: "Controller 保留为可选检索编排、关系扩展、预算建议和审计服务；默认 MCP 候选读取不经过其语义准入。",
      background: "长期偏好与融合心智模型的提炼、归并和更新只在后台加工，前台查询不重复调用后台模型。",
      backup: `${scheduleLabel(backupSettings)} 生成已选的本地备份制品。`,
    },
    backup: {
      settings: backupSettings,
      local: { ...localBackup, retentionDays: Number((backupSettings.local as any)?.retention_days ?? 14), location: String((backupSettings.local as any)?.root ?? LOCAL_BACKUP_PATH) },
      cloud: { ...cloudBackup, expectedRetentionSets: Number((backupSettings.cloud as any)?.retention_sets ?? 2), location: CLOUD_MIRROR_PATH, encryption: String((backupSettings.cloud as any)?.encryption ?? "AES-256-CBC + PBKDF2-SHA256") },
      job: backupJob,
    },
    guidanceSettings,
    runtimeSettings: { ...runtimeSettings, providers: { ...runtimeSettings.providers, primary: { ...runtimeSettings.providers?.primary, api_key: runtimeSettings.providers?.primary?.api_key ? `••••${String(runtimeSettings.providers.primary.api_key).slice(-4)}` : null }, fallbacks: (runtimeSettings.providers?.fallbacks ?? []).map((provider: any) => ({ ...provider, api_key: provider.api_key ? `••••${String(provider.api_key).slice(-4)}` : null })) } },
    context: scenarioBankVisible ? {
      status: contextIndex.status ?? "ready",
      schema: contextIndex.schema ?? "evolving-profile.context-index.v1",
      sessionCount: Array.isArray(contextIndex.sessions) ? contextIndex.sessions.length : 0,
      projectCount: Array.isArray(contextIndex.projects) ? contextIndex.projects.length : 0,
      pendingReview: scenarioStatus.pendingReview,
      reviewed: scenarioStatus.reviewed,
      qualityStatus: scenarioStatus.qualityStatus,
      pipeline: scenarioStatus.pipeline,
      executionOwner: "deterministic_projection_pending_model_review",
      externalEpModel: "coding-plan-qwen3.7-plus",
      sourceOfTruth: contextIndex.source_of_truth ?? "codex_rollout_or_ep_session_index",
      evidenceRole: "context_navigation_only",
      updatedAt: contextIndex.updated_at ?? null,
      progress: contextProgress,
      audit: contextAudit,
      graph: { nodes: contextNodes, edges: contextEdges, timeline: contextTimeline, bankRecordLinks: { available: bankLinks.length > 0, linked: Number(contextAssociations.linked_records ?? bankLinks.length), sampled: bankNodes.length, scanned: Number(contextAssociations.scanned_records ?? 0), indexedAt: contextAssociations.indexed_at ?? null, sourceIndexUpdatedAt: contextAssociations.source_index_updated_at ?? null, ...associationCoverage, snapshotOnly: true, reason: bankLinks.length > 0 ? "read_only_snapshot_not_live_bank_coverage" : "association sidecar not available" } },
    } : {
      status: "not_available_for_bank",
      schema: "evolving-profile.context-index.v1",
      sessionCount: 0, projectCount: 0, pendingReview: 0,
      qualityStatus: "unavailable", pipeline: "当前 Bank 未建立情景摘要索引",
      sourceOfTruth: "not_available_for_bank", evidenceRole: "none", updatedAt: null,
      graph: { nodes: [], edges: [], timeline: [], bankRecordLinks: { available: false, linked: 0, sampled: 0, scanned: 0, indexedAt: null, sourceIndexUpdatedAt: null, liveTotal: null, unscanned: null, coverage: "unknown", snapshotOnly: true, reason: "bank_scope_mismatch" } },
    },
  });
}
