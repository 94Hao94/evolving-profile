import { NextResponse } from "next/server";
import { readdir, readFile, stat } from "node:fs/promises";
import { promisify } from "node:util";
import { execFile } from "node:child_process";
import { homedir } from "node:os";
import path from "node:path";
import { parseCloudReadbackReceipt, summarizeCloudBackups, summarizeLocalBackups, type BackupFile, type CloudBackupSet } from "@/lib/backup-status";

const HOME = process.env.HOME ?? homedir();
const STATE_ROOT = process.env.EVOLVING_PROFILE_STATE_ROOT ?? path.join(HOME, ".evolving-profile");
const ENV_PATH = path.join(STATE_ROOT, "profiles/evolving-profile-api.env");
const PROFILE_PATH = path.join(STATE_ROOT, "codex.json");
const LOCAL_BACKUP_PATH = path.join(STATE_ROOT, "backups/managed/daily");
const WPS_CLOUD_RECEIPT_PATH = path.join(STATE_ROOT, "runtime/wps-cloud-upload-receipt.json");
const CLOUD_MIRROR_PATH = process.env.EVOLVING_PROFILE_CLOUD_MIRROR_PATH ?? path.join(STATE_ROOT, "backups/cloud-mirror");
const BACKUP_SETTINGS_PATH = path.join(STATE_ROOT, "config/backup-settings.json");
const execFileAsync = promisify(execFile);

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

export async function GET() {
  let env: Record<string, string> = {};
  let profile: Record<string, unknown> = {};
  let backupSettings: Record<string, unknown> = {};
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

  const [api, controller, localFiles, cloudReadback, backupJob] = await Promise.all([
    serviceState("http://127.0.0.1:12088/health"),
    serviceState("http://127.0.0.1:12079/health"),
    flatFiles(LOCAL_BACKUP_PATH), wpsCloudReadback(), backupJobState(),
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

  return NextResponse.json({
    schema: "evolving-profile.runtime.v1",
    model: {
      provider: env.EVOLVING_PROFILE_API_LLM_PROVIDER ?? "not_configured",
      model: env.EVOLVING_PROFILE_API_LLM_MODEL ?? "not_configured",
      baseUrl: env.EVOLVING_PROFILE_API_LLM_BASE_URL ?? "not_configured",
      apiKey: maskSecret(env.EVOLVING_PROFILE_API_LLM_API_KEY),
    },
    services: [
      { name: "Evolving Profile API", ...api },
      { name: "Query Controller", ...controller },
      { name: "Console", url: "http://127.0.0.1:9999", status: "healthy", detail: "bookmark-compatible" },
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
        ? "自动历史召回已关闭。Codex 根据入口说明按需调用 recall；复杂问题使用 research，关键结论使用 read_source。候选以分页预览返回。"
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
  });
}
