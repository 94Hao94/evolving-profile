"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useLocale } from "next-intl";
import { Activity, Bot, Cloud, Database, HardDrive, RefreshCw, Route, ShieldCheck } from "lucide-react";

type RuntimeState = {
  model: { provider: string; model: string; baseUrl: string; apiKey: string | null };
  services: Array<{ name: string; url: string; status: "healthy" | "attention" | "unavailable"; detail: string }>;
  hostIntegration: { hosts: string[]; hookStages: string[]; mcpServer: string; entry: string };
  behavior: { guidance: string; retrieval: string; controller: string; background: string; backup: string };
  backup: {
    settings?: any;
    local: { status: string; setCount: number; fileCount: number; totalBytes: number; latestSet: string | null; latestAt: string | null; latestBytes: number; latestVerified: boolean; artifacts: { database: boolean; config: boolean; capture: boolean }; retentionDays: number; location: string };
    cloud: { status: string; mirrorSetCount: number; totalBytes: number; latestSet: string | null; latestAt: string | null; ageHours: number | null; encrypted: boolean; plaintextFiles: number; wpsCache: { present: boolean; fileCount: number; timedOut?: boolean; probeSkipped?: boolean }; readback?: { observed: boolean; fileName?: string; fileId?: string; fileSize?: number; completeSize?: number; errorCode?: number; completedAt?: string | null }; expectedRetentionSets: number; location: string; encryption: string };
    job: { loaded: boolean; running: boolean; lastExitCode: number | null; schedule: string };
  };
};

const STATUS_STYLE: Record<string, string> = {
  healthy: "bg-emerald-500",
  attention: "bg-amber-500",
  unavailable: "bg-rose-500",
};

function formatBytes(value: number) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = Math.max(0, value); let index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${size >= 10 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`;
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

const CLOUD_LABEL: Record<string, string> = { observed: "已观测", unverified: "待云端回读", stale: "已滞后", missing: "未发现" };

export function EvolvingProfileRuntimeView() {
  const locale = useLocale();
  const english = !locale.startsWith("zh");
  const [state, setState] = useState<RuntimeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingBackup, setSavingBackup] = useState(false);
  const [backupMessage, setBackupMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/evolving-profile/runtime", { cache: "no-store" });
      setState(await response.json());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const saveBackupSettings = useCallback(async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!state?.backup.settings) return;
    setSavingBackup(true); setBackupMessage(null);
    try {
      const response = await fetch("/api/evolving-profile/backup-settings", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(state.backup.settings) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error || "保存失败");
      setBackupMessage("备份设置已保存并应用"); await load();
    } catch (error) { setBackupMessage(error instanceof Error ? error.message : "保存失败"); }
    finally { setSavingBackup(false); }
  }, [load, state]);

  if (loading || !state) {
    return <div className="rounded-lg border p-6 text-sm text-muted-foreground">{english ? "Loading Evolving Profile runtime configuration..." : "正在读取 Evolving Profile 运行配置…"}</div>;
  }

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{english ? "Evolving Profile Runtime Configuration" : "Evolving Profile 运行配置"}</h2>
          <p className="mt-1 text-sm text-muted-foreground">只显示当前系统实际使用的链路；密钥永不在界面显示明文。</p>
        </div>
        <button onClick={() => void load()} className="inline-flex h-9 w-9 items-center justify-center rounded-md border hover:bg-muted" title="刷新运行状态">
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <article className="rounded-lg border p-4">
          <div className="flex items-center gap-2 text-sm font-semibold"><Bot className="h-4 w-4 text-primary" />后台加工模型</div>
          <dl className="mt-4 grid grid-cols-[110px_1fr] gap-y-3 text-sm">
            <dt className="text-muted-foreground">提供商</dt><dd>{state.model.provider}</dd>
            <dt className="text-muted-foreground">模型</dt><dd>{state.model.model}</dd>
            <dt className="text-muted-foreground">API 密钥</dt><dd>{state.model.apiKey ?? "未配置"}</dd>
            <dt className="text-muted-foreground">服务地址</dt><dd className="truncate font-mono text-xs">{state.model.baseUrl}</dd>
          </dl>
        </article>
        <article className="rounded-lg border p-4">
          <div className="flex items-center gap-2 text-sm font-semibold"><Route className="h-4 w-4 text-primary" />宿主接入</div>
          <p className="mt-3 text-sm"><span className="text-muted-foreground">MCP：</span>{state.hostIntegration.mcpServer}</p>
          <p className="mt-2 text-sm"><span className="text-muted-foreground">入口：</span>{state.hostIntegration.entry}</p>
          <p className="mt-2 text-sm"><span className="text-muted-foreground">宿主：</span>{state.hostIntegration.hosts.join(" · ")}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {state.hostIntegration.hookStages.map((stage) => <span key={stage} className="rounded bg-muted px-2 py-1 font-mono text-[11px]">{stage}</span>)}
          </div>
        </article>
      </div>

      <div className="rounded-lg border p-4">
        <div className="flex items-center gap-2 text-sm font-semibold"><Activity className="h-4 w-4 text-primary" />本机服务</div>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          {state.services.map((service) => (
            <div key={service.name} className="rounded-md border p-3">
              <div className="flex items-center gap-2 text-sm font-medium"><span className={`h-2 w-2 rounded-full ${STATUS_STYLE[service.status]}`} />{service.name}</div>
              <p className="mt-2 truncate font-mono text-[11px] text-muted-foreground">{service.url}</p>
              <p className="mt-1 text-xs text-muted-foreground">{service.detail}</p>
            </div>
          ))}
        </div>
      </div>

      <article className="rounded-lg border p-4">
        <div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary" />数据与备份</div><p className="mt-2 text-sm leading-6 text-muted-foreground">{state.behavior.background}</p></div><span className={`rounded-full px-2.5 py-1 text-xs font-medium ${state.backup.job.loaded && state.backup.job.lastExitCode === 0 ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200" : "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200"}`}>{state.backup.job.schedule} · 最近退出 {state.backup.job.lastExitCode ?? "未知"}</span></div>
        <div className="mt-4 grid gap-3 lg:grid-cols-2">
          <div className="rounded-md border p-3">
            <div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2 text-sm font-medium"><HardDrive className="h-4 w-4 text-emerald-600" />本地备份</div><span className="text-xs text-emerald-700">{state.backup.local.status === "healthy" ? "正常" : "缺失"}</span></div>
            <dl className="mt-3 grid grid-cols-[90px_1fr] gap-y-2 text-xs"><dt className="text-muted-foreground">最新时间</dt><dd>{formatDate(state.backup.local.latestAt)}</dd><dt className="text-muted-foreground">备份集合</dt><dd>{state.backup.local.setCount} 套 · {state.backup.local.fileCount} 个文件</dd><dt className="text-muted-foreground">占用空间</dt><dd>{formatBytes(state.backup.local.totalBytes)} · 最近一套 {formatBytes(state.backup.local.latestBytes)}</dd><dt className="text-muted-foreground">内容</dt><dd>{state.backup.local.artifacts.database ? "数据库" : "缺数据库"} · {state.backup.local.artifacts.config ? "加密配置" : "缺配置"} · {state.backup.local.artifacts.capture ? "加密回执" : "无回执快照"}</dd><dt className="text-muted-foreground">校验</dt><dd>{state.backup.local.latestVerified ? "SHA-256 清单存在" : "未发现校验清单"}</dd><dt className="text-muted-foreground">保留策略</dt><dd>{state.backup.local.retentionDays} 天</dd></dl>
            <p className="mt-3 break-all font-mono text-[10px] text-muted-foreground">{state.backup.local.location}</p>
          </div>
          <div className="rounded-md border p-3">
            <div className="flex items-center justify-between gap-2"><div className="flex items-center gap-2 text-sm font-medium"><Cloud className="h-4 w-4 text-sky-600" />云备份镜像</div><span className={`text-xs ${state.backup.cloud.status === "observed" ? "text-emerald-700" : "text-amber-700"}`}>{CLOUD_LABEL[state.backup.cloud.status] ?? state.backup.cloud.status}</span></div>
            <dl className="mt-3 grid grid-cols-[90px_minmax(0,1fr)] gap-y-2 text-xs"><dt className="text-muted-foreground">最新镜像</dt><dd>{formatDate(state.backup.cloud.latestAt)}{state.backup.cloud.ageHours != null ? ` · ${state.backup.cloud.ageHours} 小时前` : ""}</dd><dt className="text-muted-foreground">备份集合</dt><dd>{state.backup.cloud.mirrorSetCount} 套 / 预期保留 {state.backup.cloud.expectedRetentionSets} 套</dd><dt className="text-muted-foreground">占用空间</dt><dd>{formatBytes(state.backup.cloud.totalBytes)}</dd><dt className="text-muted-foreground">加密</dt><dd>{state.backup.cloud.encrypted ? state.backup.cloud.encryption : "未完整核实"} · 明文制品 {state.backup.cloud.plaintextFiles}</dd><dt className="text-muted-foreground">WPS 文件</dt><dd className="break-all">{state.backup.cloud.readback?.observed ? state.backup.cloud.readback.fileName : "未取得上传完成回执"}</dd><dt className="text-muted-foreground">上传回执</dt><dd>{state.backup.cloud.readback?.observed ? `完整 ${formatBytes(state.backup.cloud.readback.completeSize ?? 0)} · 错误码 0` : "未知"}</dd><dt className="text-muted-foreground">WPS 文件 ID</dt><dd className="break-all font-mono">{state.backup.cloud.readback?.fileId ?? "未知"}</dd><dt className="text-muted-foreground">缓存扫描</dt><dd>{state.backup.cloud.wpsCache.probeSkipped ? "已跳过 · 以云端上传回执为准" : state.backup.cloud.wpsCache.timedOut ? "读取超时" : state.backup.cloud.wpsCache.present ? `${state.backup.cloud.wpsCache.fileCount} 个可见入口` : "目录不可读"}</dd></dl>
            <p className="mt-3 text-xs leading-5 text-muted-foreground">云端正常必须同时满足：本地加密集合完整、WPS 上传完成字节等于文件大小、错误码为 0，并取得云端文件 ID。</p>
            <p className="mt-2 break-all font-mono text-[10px] text-muted-foreground">{state.backup.cloud.location}</p>
          </div>
        </div>
      </article>

      <article className="rounded-lg border p-4">
        <div className="flex items-center justify-between gap-3"><div><h3 className="text-sm font-semibold">备份设置</h3><p className="mt-1 text-xs text-muted-foreground">本地计划和保留策略可编辑；云端镜像单独管理，不自动覆盖本地规则。</p></div>{backupMessage && <span className="text-xs text-emerald-700">{backupMessage}</span>}</div>
        {state.backup.settings && <form onSubmit={saveBackupSettings} className="mt-4 grid gap-4 md:grid-cols-2 text-sm">
          <label className="space-y-1"><span className="text-xs text-muted-foreground">本地备份位置</span><input className="h-9 w-full rounded border bg-background px-2 font-mono text-xs" value={state.backup.settings.local?.root ?? ""} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, local:{...state.backup.settings.local, root:e.target.value}}}})} /></label>
          <label className="space-y-1"><span className="text-xs text-muted-foreground">周期</span><select className="h-9 w-full rounded border bg-background px-2" value={state.backup.settings.schedule?.mode ?? "daily"} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, schedule:{...state.backup.settings.schedule, mode:e.target.value}}}})}><option value="daily">每日</option><option value="weekly">每周</option><option value="monthly">每月</option></select></label>
          <label className="space-y-1"><span className="text-xs text-muted-foreground">执行时间（小时 / 分钟）</span><div className="flex gap-2"><input type="number" min="0" max="23" className="h-9 w-20 rounded border bg-background px-2" value={state.backup.settings.schedule?.hour ?? 3} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, schedule:{...state.backup.settings.schedule, hour:Number(e.target.value)}}}})} /><input type="number" min="0" max="59" className="h-9 w-20 rounded border bg-background px-2" value={state.backup.settings.schedule?.minute ?? 25} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, schedule:{...state.backup.settings.schedule, minute:Number(e.target.value)}}}})} /></div></label>
          {state.backup.settings.schedule?.mode === "weekly" && <label className="space-y-1"><span className="text-xs text-muted-foreground">每周执行日</span><select className="h-9 w-full rounded border bg-background px-2" value={state.backup.settings.schedule?.weekday ?? 1} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, schedule:{...state.backup.settings.schedule, weekday:Number(e.target.value)}}}})}>{["周日","周一","周二","周三","周四","周五","周六"].map((label, value) => <option key={label} value={value}>{label}</option>)}</select></label>}
          {state.backup.settings.schedule?.mode === "monthly" && <label className="space-y-1"><span className="text-xs text-muted-foreground">每月执行日</span><input type="number" min="1" max="28" className="h-9 w-28 rounded border bg-background px-2" value={state.backup.settings.schedule?.day ?? 1} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, schedule:{...state.backup.settings.schedule, day:Number(e.target.value)}}}})} /></label>}
          <label className="space-y-1"><span className="text-xs text-muted-foreground">本地保留天数 / 最大套数</span><div className="flex gap-2"><input type="number" min="1" max="3650" className="h-9 w-28 rounded border bg-background px-2" value={state.backup.settings.local?.retention_days ?? 14} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, local:{...state.backup.settings.local, retention_days:Number(e.target.value)}}}})} /><input type="number" min="1" max="1000" className="h-9 w-28 rounded border bg-background px-2" value={state.backup.settings.local?.max_sets ?? 14} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, local:{...state.backup.settings.local, max_sets:Number(e.target.value)}}}})} /></div></label>
          <div className="flex flex-wrap gap-4 text-xs md:col-span-2"><label><input type="checkbox" checked={state.backup.settings.local?.database ?? true} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, local:{...state.backup.settings.local, database:e.target.checked}}}})} /> 数据库</label><label><input type="checkbox" checked={state.backup.settings.local?.config ?? true} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, local:{...state.backup.settings.local, config:e.target.checked}}}})} /> 加密配置</label><label><input type="checkbox" checked={state.backup.settings.local?.capture ?? true} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, local:{...state.backup.settings.local, capture:e.target.checked}}}})} /> 加密回执</label><label><input type="checkbox" checked={state.backup.settings.local?.verify_checksum ?? true} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, local:{...state.backup.settings.local, verify_checksum:e.target.checked}}}})} /> SHA-256 校验</label></div>
          <label className="space-y-1"><span className="text-xs text-muted-foreground">云端预期保留套数（独立策略）</span><input type="number" min="0" max="1000" className="h-9 w-32 rounded border bg-background px-2" value={state.backup.settings.cloud?.retention_sets ?? 2} onChange={(e) => setState({...state, backup:{...state.backup, settings:{...state.backup.settings, cloud:{...state.backup.settings.cloud, retention_sets:Number(e.target.value)}}}})} /></label>
          <div className="flex items-end"><button disabled={savingBackup} className="rounded bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50">{savingBackup ? "保存中…" : "保存并应用"}</button></div>
        </form>}
      </article>

      <div className="grid gap-4 lg:grid-cols-2">
        <article className="rounded-lg border p-4">
          <div className="flex items-center gap-2 text-sm font-semibold"><ShieldCheck className="h-4 w-4 text-primary" />前台边界</div>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{state.behavior.guidance}</p>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{state.behavior.retrieval}</p>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{state.behavior.controller}</p>
        </article>
        <article className="rounded-lg border p-4">
          <div className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-primary" />备份说明</div>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">{state.behavior.backup}</p>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">份数按同一时间戳的一组数据库、配置、回执和校验清单计算，不把每个文件误算成一份备份。</p>
        </article>
      </div>
    </section>
  );
}
