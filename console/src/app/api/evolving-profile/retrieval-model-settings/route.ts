import { NextResponse } from "next/server";
import { access, mkdir, readFile, readdir, rename, stat, unlink, writeFile } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { homedir } from "node:os";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const ROOT = process.env.EVOLVING_PROFILE_STATE_ROOT ?? path.join(process.env.HOME ?? homedir(), ".evolving-profile");
const SETTINGS = path.join(ROOT, "config/runtime-settings.json");
const OVERLAY = path.join(ROOT, "config/retrieval-models.env");
const ENV = path.join(ROOT, "profiles/evolving-profile-api.env");
const execFileAsync = promisify(execFile);

function merge(base: any, value: any): any {
  if (!value || typeof value !== "object" || Array.isArray(value)) return base;
  const result = { ...base };
  for (const [key, item] of Object.entries(value)) result[key] = item && typeof item === "object" && !Array.isArray(item) && base[key] && typeof base[key] === "object" ? merge(base[key], item) : item;
  return result;
}

function mask(value: any) {
  const copy = structuredClone(value);
  for (const model of [copy.embedding, copy.reranker]) if (model?.api_key) model.api_key = `••••${String(model.api_key).slice(-4)}`;
  return copy;
}

function envValue(value: unknown) {
  const text = String(value ?? "");
  if (/[\r\n\0]/.test(text)) throw new Error("模型配置包含不允许的换行或空字符");
  return `"${text.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

async function modelFiles(root: string, depth = 0): Promise<string[]> {
  if (depth > 3) return [];
  try {
    const entries = await readdir(root, { withFileTypes: true });
    const files: string[] = [];
    for (const entry of entries) {
      const full = path.join(root, entry.name);
      if (entry.isFile()) files.push(entry.name.toLowerCase());
      else if (entry.isDirectory() && !entry.name.startsWith(".")) files.push(...(await modelFiles(full, depth + 1)).map((item) => `${entry.name}/${item}`));
    }
    return files;
  } catch { return []; }
}

async function validateLocalModel(model: any, kind: "embedding" | "reranker") {
  const localPath = String(model?.local_path ?? "").trim();
  if (!localPath) return;
  const files = await modelFiles(localPath);
  const hasConfig = files.some((file) => file === "config.json" || file.endsWith("/config.json"));
  const hasTokenizer = files.some((file) => ["tokenizer.json", "tokenizer.model", "vocab.txt", "spiece.model"].some((name) => file === name || file.endsWith(`/${name}`)));
  const hasWeights = files.some((file) => /(^|\/)(model\.onnx|onnx\/model\.onnx|pytorch_model.*\.(bin|safetensors)|model.*\.(bin|safetensors|gguf))$/.test(file));
  if (!hasConfig) throw new Error(`${kind === "embedding" ? "向量" : "重排"}模型目录缺少 config.json`);
  if (!hasTokenizer) throw new Error(`${kind === "embedding" ? "向量" : "重排"}模型目录缺少 tokenizer 文件`);
  if (!hasWeights) throw new Error(`${kind === "embedding" ? "向量" : "重排"}模型目录缺少可加载权重文件`);
  if (kind === "embedding" && Number.isInteger(model.dimensions)) {
    const configFile = files.find((file) => file === "config.json" || file.endsWith("/config.json"));
    if (configFile === "config.json") {
      const config = JSON.parse(await readFile(path.join(localPath, configFile), "utf8"));
      const detected = Number(config.hidden_size ?? config.embedding_size ?? config.projection_dim ?? 0);
      if (detected > 0 && Number(model.dimensions) !== detected) throw new Error(`向量维度不匹配：目录检测为 ${detected}，当前填写为 ${model.dimensions}`);
    }
  }
}

async function current() {
  const envText = await readFile(ENV, "utf8");
  const env = Object.fromEntries(envText.split(/\r?\n/).filter((line) => line && !line.trimStart().startsWith("#") && line.includes("=")).map((line) => { const index = line.indexOf("="); return [line.slice(0, index), line.slice(index + 1).trim().replace(/^['"]|['"]$/g, "")]; }));
  const base = {
    embedding: { enabled: true, mode: "local", provider: env.EVOLVING_PROFILE_API_EMBEDDINGS_PROVIDER || "onnx", model: env.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MODEL_ID || "intfloat/multilingual-e5-small", local_path: env.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MODEL_PATH || "", dimensions: Number(env.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_DIMENSIONS || 384), max_tokens: Number(env.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MAX_TOKENS || 512), device: "cpu", profile_id: "embedding-default", status: "configured" },
    reranker: { enabled: env.EVOLVING_PROFILE_API_RERANKER_PROVIDER !== "rrf", mode: "local", provider: env.EVOLVING_PROFILE_API_RERANKER_PROVIDER || "rrf", model: env.EVOLVING_PROFILE_API_RERANKER_LOCAL_MODEL || "BAAI/bge-reranker-base", local_path: "", device: "cpu", profile_id: "reranker-default", status: env.EVOLVING_PROFILE_API_RERANKER_PROVIDER === "rrf" ? "configured_but_inactive" : "configured" },
    embedding_profiles: [], reranker_profiles: [],
    fusion: { enabled: true, algorithm: "rrf", profile_id: "fusion-rrf" },
    judge: { enabled: false, provider: "jev", mode: "api", base_url: "", model: "", api_key: "", timeout_ms: 5000, max_tokens: 600, mode_policy: "off", fallback: "rules", send_scope: "metadata_summary", risk_gate_enabled: false, status: "disabled" },
  };
  let settings: any = {};
  try { settings = JSON.parse(await readFile(SETTINGS, "utf8")).retrieval_models ?? {}; } catch { /* first-run uses environment defaults */ }
  const result = merge(base, settings);
  if (!Array.isArray(result.embedding_profiles) || result.embedding_profiles.length === 0) result.embedding_profiles = [{ ...result.embedding }];
  if (!Array.isArray(result.reranker_profiles) || result.reranker_profiles.length === 0) result.reranker_profiles = [{ ...result.reranker }];
  result.embedding.api_key = env.EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_API_KEY || "";
  result.embedding.base_url = env.EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_BASE_URL || "";
  result.reranker.api_key = env.EVOLVING_PROFILE_API_RERANKER_TEI_API_KEY || "";
  result.reranker.base_url = env.EVOLVING_PROFILE_API_RERANKER_TEI_URL || "";
  return result;
}

async function validate(models: any) {
  for (const name of ["embedding", "reranker"]) {
    const model = models?.[name];
    if (!model || !["local", "api"].includes(model.mode) || typeof model.enabled !== "boolean" || !String(model.model ?? "").trim()) throw new Error(`检索模型配置无效：${name}`);
    if (model.mode === "api" && !String(model.base_url ?? "").trim()) throw new Error(`${name === "embedding" ? "向量模型" : "重排模型"}使用线上 API 时必须填写 API 地址`);
    if (model.local_path) {
      const path = String(model.local_path);
      if (!path.startsWith("/") || path.includes("..")) throw new Error("本地模型目录必须是有效的绝对路径");
      const info = await stat(path).catch(() => null);
      if (!info?.isDirectory()) throw new Error("本地模型目录不存在或不是目录");
      await access(path).catch(() => { throw new Error("本地模型目录不可读"); });
    }
    await validateLocalModel(model, name as "embedding" | "reranker");
  }
  for (const [kind, profiles] of [["embedding", models.embedding_profiles], ["reranker", models.reranker_profiles]] as const) {
    if (!Array.isArray(profiles)) throw new Error(`${kind} 配置档案必须是数组`);
    const ids = new Set<string>();
    for (const profile of profiles) {
      if (!profile?.profile_id || ids.has(String(profile.profile_id))) throw new Error(`${kind} 配置档案 ID 重复或为空`);
      ids.add(String(profile.profile_id));
      if (!String(profile.model ?? "").trim()) throw new Error(`${kind} 配置档案缺少模型名称`);
      await validateLocalModel(profile, kind);
    }
  }
  if (!Number.isInteger(models.embedding.dimensions) || models.embedding.dimensions < 1 || models.embedding.dimensions > 65536) throw new Error("向量维度无效");
  if (!Number.isInteger(models.judge.timeout_ms) || models.judge.timeout_ms < 500 || models.judge.timeout_ms > 60000) throw new Error("JEV 超时必须在 500 到 60000 毫秒之间");
  if (!Number.isInteger(models.judge.max_tokens) || models.judge.max_tokens < 32 || models.judge.max_tokens > 8000) throw new Error("JEV 最大输出长度无效");
  if (!["off", "shadow", "assist", "enforce"].includes(models.judge.mode_policy)) throw new Error("JEV 运行模式无效");
  if (!models.judge.enabled && models.judge.risk_gate_enabled) throw new Error("须先启用 JEV，才能启用风险确认门");
}

function modelEnv(models: any) {
  const embedding = models.embedding;
  const reranker = models.reranker;
  const values: Record<string, string> = {};
  if (embedding.mode === "local") {
    values.EVOLVING_PROFILE_API_EMBEDDINGS_PROVIDER = embedding.provider === "local" ? "local" : "onnx";
    if (embedding.provider === "local") values.EVOLVING_PROFILE_API_EMBEDDINGS_LOCAL_MODEL = embedding.model;
    else {
      values.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MODEL_ID = embedding.model;
      values.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_DIMENSIONS = String(embedding.dimensions);
      values.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MAX_TOKENS = String(embedding.max_tokens || 512);
      if (embedding.local_path) {
        values.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_MODEL_PATH = path.join(embedding.local_path, "onnx/model.onnx");
        values.EVOLVING_PROFILE_API_EMBEDDINGS_ONNX_TOKENIZER_NAME_OR_PATH = embedding.local_path;
      }
    }
  } else {
    values.EVOLVING_PROFILE_API_EMBEDDINGS_PROVIDER = embedding.provider || "openai";
    values.EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_MODEL = embedding.model;
    values.EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_BASE_URL = embedding.base_url;
    values.EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_API_KEY = embedding.api_key || "";
    if (embedding.dimensions) values.EVOLVING_PROFILE_API_EMBEDDINGS_OPENAI_DIMENSIONS = String(embedding.dimensions);
  }
  if (!reranker.enabled) values.EVOLVING_PROFILE_API_RERANKER_PROVIDER = "rrf";
  else if (reranker.mode === "local") {
    values.EVOLVING_PROFILE_API_RERANKER_PROVIDER = "local";
    values.EVOLVING_PROFILE_API_RERANKER_LOCAL_MODEL = reranker.local_path || reranker.model;
  } else {
    values.EVOLVING_PROFILE_API_RERANKER_PROVIDER = "tei";
    values.EVOLVING_PROFILE_API_RERANKER_TEI_URL = reranker.base_url;
    values.EVOLVING_PROFILE_API_RERANKER_TEI_API_KEY = reranker.api_key || "";
  }
  return Object.entries(values).map(([key, value]) => `${key}=${envValue(value)}`).join("\n") + "\n";
}

export async function GET() {
  try { return NextResponse.json(mask(await current())); }
  catch (error) { return NextResponse.json({ error: error instanceof Error ? error.message : "模型配置读取失败" }, { status: 500 }); }
}

export async function POST(request: Request) {
  let settingsCurrent: any = {};
  try { settingsCurrent = JSON.parse(await readFile(SETTINGS, "utf8")); } catch { /* first-run */ }
  const incoming = await request.json();
  const oldModels = await current();
  const models = merge(oldModels, incoming);
  for (const key of ["embedding", "reranker", "judge"]) if (incoming?.[key]?.api_key?.startsWith("••••")) models[key].api_key = oldModels[key].api_key;
  try {
    await validate(models);
    const nextSettings = { ...settingsCurrent, retrieval_models: models, updated_at: new Date().toISOString() };
    await mkdir(path.dirname(SETTINGS), { recursive: true });
    const settingsTemp = `${SETTINGS}.${randomUUID()}.tmp`;
    const envTemp = `${OVERLAY}.${randomUUID()}.tmp`;
    try {
      await writeFile(settingsTemp, JSON.stringify(nextSettings, null, 2) + "\n", { mode: 0o600, flag: "wx" });
      await writeFile(envTemp, modelEnv(models), { mode: 0o600, flag: "wx" });
      await rename(envTemp, OVERLAY);
      await rename(settingsTemp, SETTINGS);
    } finally {
      await unlink(settingsTemp).catch(() => undefined);
      await unlink(envTemp).catch(() => undefined);
    }
    let applied = false;
    let applyMessage = "模型设置已保存；API 服务重启后应用。";
    try {
      await execFileAsync("launchctl", ["kickstart", "-k", `gui/${process.getuid?.() ?? 501}/com.evolving-profile.api-shadow`], { timeout: 15000 });
      const deadline = Date.now() + 30000;
      let health: Response | null = null;
      while (Date.now() < deadline) {
        try {
          health = await fetch("http://127.0.0.1:12088/health", { cache: "no-store", signal: AbortSignal.timeout(2500) });
          if (health.ok) break;
        } catch { /* API is still loading the selected local model. */ }
        await new Promise((resolve) => setTimeout(resolve, 750));
      }
      if (!health) throw new Error("api_health_timeout");
      applied = health.ok;
      applyMessage = applied ? "模型设置已应用，EP API 已恢复健康。" : "模型设置已保存，但 API 健康检查未通过；请查看服务状态。";
    } catch {
      applyMessage = "模型设置已保存，但自动重启或健康检查未确认；请查看服务状态。";
    }
    return NextResponse.json({ ...mask(models), saved: true, applied, message: applyMessage });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "检索模型配置失败" }, { status: 400 });
  }
}
