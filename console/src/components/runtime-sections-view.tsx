"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useLocale } from "next-intl";
import {
  Activity,
  Bot,
  CheckCircle2,
  Cloud,
  Database,
  FolderOpen,
  HardDrive,
  Route,
  Save,
  ShieldCheck,
} from "lucide-react";

import { inlineUiText } from "@/lib/inline-i18n";
type Section = "runtime" | "memory" | "models" | "rag" | "providers" | "scenario" | "backup";

type RuntimeState = any;
const STATUS_STYLE: Record<string, string> = {
  healthy: "bg-emerald-500",
  attention: "bg-amber-500",
  unavailable: "bg-rose-500",
};

const moduleLabels: Record<string, string> = {
  facts: inlineUiText("事实"),
  experiences: inlineUiText("经历"),
  entities: inlineUiText("实体与关系"),
  preferences: inlineUiText("多维度偏好"),
  scenario_summary: inlineUiText("情景摘要"),
  mental_models: inlineUiText("融合心智模型"),
  source_readback: inlineUiText("原文回读"),
  background_reflection: inlineUiText("后台记录与反思"),
  agent_process_memory: inlineUiText("Agent 过程记忆"),
  agent_process_trajectory: inlineUiText("原始轨迹"),
  agent_process_observation: inlineUiText("过程观察"),
  agent_process_failure_episode: inlineUiText("失败事件"),
  agent_process_repair_pattern: inlineUiText("修复模式"),
  agent_process_capability: inlineUiText("能力观测"),
  agent_process_strategy: inlineUiText("可复用过程策略"),
  agent_process_revalidation: inlineUiText("迁移与再验证"),
};

export function RuntimeSectionsView({ section }: { section: Section }) {
  const english = !useLocale().startsWith("zh");
  const [state, setState] = useState<RuntimeState | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [directoryMessage, setDirectoryMessage] = useState<string | null>(null);
  const load = useCallback(
    async () =>
      setState(
        await fetch("/api/evolving-profile/runtime", { cache: "no-store" }).then((r) => r.json())
      ),
    []
  );
  useEffect(() => {
    void load();
  }, [load]);
  if (!state)
    return <div className="rounded-lg border p-6 text-sm text-muted-foreground">{english ? "Loading configuration…" : inlineUiText("正在读取配置…")}</div>;

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setMessage(null);
    const response = await fetch("/api/evolving-profile/runtime-settings", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(state.runtimeSettings),
    });
    const body = await response.json();
    setMessage(response.ok ? inlineUiText("配置已保存，新一轮入口生效") : body.error || inlineUiText("保存失败"));
    if (response.ok) await load();
  };

  const updateModule = (name: string, action: string, checked: boolean) =>
    setState({
      ...state,
      runtimeSettings: {
        ...state.runtimeSettings,
        modules: {
          ...state.runtimeSettings.modules,
          [name]: { ...state.runtimeSettings.modules[name], [action]: checked, ...(action === "retrieve" && !checked ? { inject: false } : {}) },
        },
      },
    });
  const chooseDirectory = async () => {
    setDirectoryMessage(inlineUiText("正在打开系统目录选择器…"));
    const response = await fetch("/api/evolving-profile/select-directory", { method: "POST" });
    const body = await response.json();
    if (body.canceled) return setDirectoryMessage(inlineUiText("已取消选择"));
    if (!response.ok) return setDirectoryMessage(body.error || inlineUiText("目录选择失败"));
    setState({
      ...state,
      runtimeSettings: {
        ...state.runtimeSettings,
        routing: { ...state.runtimeSettings.routing, external_rag_enabled: true },
        rag: { ...state.runtimeSettings.rag, enabled: true, root_path: body.path },
      },
    });
    setDirectoryMessage(inlineUiText("目录已选择，请保存配置"));
  };

  if (section === "runtime") return <RuntimeOverview state={state} />;
  if (section === "memory") {
    const userModules = Object.entries(state.runtimeSettings.modules).filter(([name]) => !name.startsWith("agent_process_"));
    const agentSettings = state.runtimeSettings.modules.agent_process_memory ?? { record: true, retrieve: true, inject: true };
    const agentDimensions = Object.entries(state.runtimeSettings.modules).filter(([name]) => name.startsWith("agent_process_") && name !== "agent_process_memory");
    const moduleCard = ([name, settings]: [string, any]) => <div className="rounded-lg border p-4" key={name}><div className="font-medium">{moduleLabels[name] ?? name}</div><div className="mt-3 flex flex-wrap gap-3 text-xs">{(["record", "retrieve", "inject"] as const).map((action) => <label key={action} className={action === "inject" && !settings.retrieve ? "text-muted-foreground" : undefined}><input type="checkbox" checked={Boolean(settings[action])} disabled={action === "inject" && !settings.retrieve} onChange={(e) => updateModule(name, action, e.target.checked)} /> {action === "record" ? inlineUiText("记录") : action === "retrieve" ? inlineUiText("检索") : inlineUiText("注入")}</label>)}</div>{name.startsWith("agent_process_") && name !== "agent_process_memory" && !settings.record && <p className="mt-2 text-[11px] text-amber-700">{inlineUiText("已关闭记录：不会产生新的该类过程记忆，已有数据不会删除。")}</p>}</div>;
    return <section className="space-y-5"><form onSubmit={save} className="space-y-5">
      <SectionHeading icon={<Database className="h-4 w-4" />} title={english ? "User memory" : inlineUiText("用户记忆")} description={english ? "Runtime switches for facts, experiences, entities, preferences, scenario summaries, and source readback." : inlineUiText("事实、经历、实体、偏好、情景摘要和原文回读的运行开关。")} message={message} />
      <div className="grid gap-3 md:grid-cols-2">{userModules.map((entry) => moduleCard(entry as [string, any]))}</div>
      <BudgetFields state={state} setState={setState} />
      <SaveButton />
    </form>
    <form onSubmit={save} className="rounded-lg border p-5"><SectionHeading icon={<Bot className="h-4 w-4" />} title={inlineUiText("智能体记忆")} description={inlineUiText("总控下按原始轨迹、失败事件、修复模式、能力观测、过程策略和再验证分别控制记录、检索与注入；关闭不会删除已有数据。")} message={message} /><div className="rounded-lg border p-4">{moduleCard(["agent_process_memory", agentSettings])}</div><div className="mt-3 grid gap-3 md:grid-cols-2">{agentDimensions.map((entry) => <div key={entry[0]}>{moduleCard(entry as [string, any])}</div>)}</div><div className="mt-3 rounded border bg-muted/30 p-3 text-xs text-muted-foreground">{inlineUiText("依赖提示：原始轨迹和过程观察是失败事件的来源；失败事件支撑修复模式；修复模式与验证结果支撑可复用过程策略。关闭上游记录不会删除下游历史，但会停止新增派生记录。")}</div><div className="mt-4 grid grid-cols-2 gap-2 text-sm"><div className="rounded border p-3"><div className="text-xs text-muted-foreground">{inlineUiText("过程记录")}</div><div className="mt-1 text-lg font-semibold">{state.processMemory?.record_count ?? 0}</div></div><div className="rounded border p-3"><div className="text-xs text-muted-foreground">{inlineUiText("失败事件")}</div><div className="mt-1 text-lg font-semibold">{state.processMemory?.by_kind?.episode ?? 0}</div></div><div className="rounded border p-3"><div className="text-xs text-muted-foreground">{inlineUiText("修复模式")}</div><div className="mt-1 text-lg font-semibold">{state.processMemory?.by_kind?.pattern ?? 0}</div></div><div className="rounded border p-3"><div className="text-xs text-muted-foreground">{inlineUiText("可复用过程策略")}</div><div className="mt-1 text-lg font-semibold">{state.processMemory?.by_kind?.skill ?? 0}</div></div></div><div className="mt-4"><SaveButton /></div></form>
    </section>;
  }
  if (section === "models") return <RetrievalModelsPanel state={state} setState={setState} />;
  if (section === "rag")
    return (
      <RagPanel
        state={state}
        setState={setState}
        chooseDirectory={chooseDirectory}
        directoryMessage={directoryMessage}
        onSave={save}
        message={message}
      />
    );
  if (section === "providers") return <ProviderPanel state={state} />;
  if (section === "scenario") return <ScenarioPanel state={state} />;
  return (
    <BackupPanel
      state={state}
      setState={setState}
      onSave={async () => {
        const response = await fetch("/api/evolving-profile/backup-settings", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(state.backup.settings),
        });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(body.error || inlineUiText("备份设置保存失败"));
        setMessage(inlineUiText("备份设置已保存并应用"));
        await load();
      }}
      message={message}
    />
  );
}

function RagPanel({ state, setState, chooseDirectory, directoryMessage, onSave, message }: any) {
  const rag = state.runtimeSettings.rag;
  const models = state.runtimeSettings.retrieval_models;
  const update = (field: string, value: any) =>
    setState({
      ...state,
      runtimeSettings: { ...state.runtimeSettings, rag: { ...rag, [field]: value } },
    });
  const rerankReady = Boolean(models?.reranker?.enabled && models?.reranker?.model);
  return (
    <form onSubmit={onSave} className="space-y-4">
      <SectionHeading
        icon={<FolderOpen className="h-4 w-4" />}
        title={inlineUiText("外部 RAG")}
        description={inlineUiText("只读取外部资料目录，不进入 EP Bank。")}
        message={message}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={Boolean(rag.enabled)}
            onChange={(e) =>
              setState({
                ...state,
                runtimeSettings: {
                  ...state.runtimeSettings,
                  rag: { ...rag, enabled: e.target.checked },
                  routing: {
                    ...state.runtimeSettings.routing,
                    external_rag_enabled: e.target.checked,
                  },
                },
              })
            }
          />
          {inlineUiText("启用外部 RAG")}
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">{inlineUiText("资料目录")}</span>
          <div className="flex gap-2">
            <input
              readOnly
              className="h-9 min-w-0 flex-1 rounded border bg-background px-2 font-mono text-xs"
              value={rag.root_path}
              placeholder={inlineUiText("点击按钮选择目录")}
            />
            <button
              type="button"
              onClick={() => void chooseDirectory()}
              className="inline-flex items-center gap-1 rounded border px-3 text-xs"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              {inlineUiText("选择目录")}
            </button>
          </div>
          {directoryMessage && (
            <span className="text-xs text-muted-foreground">{directoryMessage}</span>
          )}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={rag.lexical_enabled ?? true}
            onChange={(e) => update("lexical_enabled", e.target.checked)}
          />
          {inlineUiText("词法检索")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={rag.vector_enabled ?? true}
            onChange={(e) => update("vector_enabled", e.target.checked)}
          />
          {inlineUiText("向量检索")}
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={rag.rerank_enabled ?? true}
            onChange={(e) => update("rerank_enabled", e.target.checked)}
          />
          Re-rank
        </label>
        <label className="space-y-1">
          <span className="text-xs text-muted-foreground">Top-K</span>
          <input
            type="number"
            min="1"
            max="100"
            className="h-9 w-24 rounded border bg-background px-2"
            value={rag.top_k ?? 20}
            onChange={(e) => update("top_k", Number(e.target.value))}
          />
        </label>
      </div>
      <div className="grid gap-3 rounded-lg border p-4 md:grid-cols-2">
        <label className="space-y-1 text-xs">
          <span>{inlineUiText("绑定 Embedding 配置")}</span>
          <select
            className="h-9 w-full rounded border bg-background px-2 font-mono text-xs"
            value={rag.embedding_profile_id ?? models?.embedding?.profile_id}
            onChange={(e) => update("embedding_profile_id", e.target.value)}
          >
            {(models?.embedding_profiles?.length ? models.embedding_profiles : [models?.embedding]).filter(Boolean).map((profile:any) => (
              <option key={profile.profile_id} value={profile.profile_id}>
                {profile.profile_id} · {profile.model}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-xs">
          <span>{inlineUiText("绑定 Rerank 配置")}</span>
          <select
            className="h-9 w-full rounded border bg-background px-2 font-mono text-xs"
            value={rag.reranker_profile_id ?? models?.reranker?.profile_id}
            onChange={(e) => update("reranker_profile_id", e.target.value)}
          >
            {(models?.reranker_profiles?.length ? models.reranker_profiles : [models?.reranker]).filter(Boolean).map((profile:any) => (
              <option key={profile.profile_id} value={profile.profile_id}>
                {profile.profile_id} · {profile.model}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div
        className={`rounded-lg border p-4 text-xs ${rag.rerank_enabled && !rerankReady ? "border-amber-300 bg-amber-50 text-amber-900" : "border-dashed text-muted-foreground"}`}
      >
        {rag.rerank_enabled && !rerankReady
          ? inlineUiText("当前 Re-rank 开关已打开，但未启用可加载的 Rerank 模型；实际检索会回退为候选顺序，建议先到“检索与判断模型”启用并验证模型。")
          : inlineUiText("RAG 会按上面的绑定读取检索与判断模型；更换 Embedding 后需重建外部索引，避免旧向量与新维度混用。")}
      </div>
      <BudgetFields state={state} setState={setState} />
      <SaveButton />
    </form>
  );
}
function SectionHeading({ icon, title, description, message }: any) {
  return (
    <div className="flex items-start justify-between gap-4 border-b pb-4">
      <div>
        <div className="flex items-center gap-2 text-sm font-semibold">
          {icon}
          {title}
        </div>
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      </div>
      {message && <span className="text-xs text-emerald-700">{message}</span>}
    </div>
  );
}
function SaveButton() {
  return (
    <button className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm text-primary-foreground">
      <Save className="h-4 w-4" />
      {inlineUiText("保存配置")}
    </button>
  );
}
function BudgetFields({ state, setState }: any) {
  return (
    <div className="grid gap-4 md:grid-cols-3">
      <NumberField
        label={inlineUiText("EP Token 预算")}
        value={state.runtimeSettings.budgets.ep_total_tokens ?? 4000}
        onChange={(value: number) =>
          setState({
            ...state,
            runtimeSettings: {
              ...state.runtimeSettings,
              budgets: { ...state.runtimeSettings.budgets, ep_total_tokens: value },
            },
          })
        }
      />
      <NumberField
        label={inlineUiText("RAG Token 预算")}
        value={state.runtimeSettings.budgets.rag_total_tokens ?? 4000}
        onChange={(value: number) =>
          setState({
            ...state,
            runtimeSettings: {
              ...state.runtimeSettings,
              budgets: { ...state.runtimeSettings.budgets, rag_total_tokens: value },
            },
          })
        }
      />
      <NumberField
        label={inlineUiText("总 Token 上限")}
        value={state.runtimeSettings.budgets.total_tokens ?? 6000}
        onChange={(value: number) =>
          setState({
            ...state,
            runtimeSettings: {
              ...state.runtimeSettings,
              budgets: { ...state.runtimeSettings.budgets, total_tokens: value },
            },
          })
        }
      />
    </div>
  );
}
function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="space-y-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      <input
        type="number"
        className="block h-9 w-32 rounded border bg-background px-2"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </label>
  );
}
function RetrievalModelsPanel({ state, setState }: any) {
  const [message, setMessage] = useState<string | null>(null);
  const models = state.runtimeSettings.retrieval_models;
  const update = (group: string, field: string, value: any) =>
    setState({
      ...state,
      runtimeSettings: {
        ...state.runtimeSettings,
        retrieval_models: { ...models, [group]: { ...models[group], [field]: value } },
      },
    });
  const save = async () => {
    const response = await fetch("/api/evolving-profile/retrieval-model-settings", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(models),
    });
    const body = await response.json();
    setMessage(response.ok ? body.message || inlineUiText("检索与判断模型配置已保存") : body.error || inlineUiText("保存失败"));
  };
  const cloneProfile = (kind: "embedding" | "reranker", profile: any) => {
    const key = `${kind}_profiles`;
    const profiles = Array.isArray(models[key]) ? models[key] : [models[kind]];
    const baseId = String(profile?.profile_id || kind);
    let profileId = `${baseId}-copy`;
    let index = 2;
    while (profiles.some((item: any) => item.profile_id === profileId)) profileId = `${baseId}-copy-${index++}`;
    setState({
      ...state,
      runtimeSettings: {
        ...state.runtimeSettings,
        retrieval_models: { ...models, [key]: [...profiles, { ...profile, profile_id: profileId, status: "draft" }] },
      },
    });
  };
  const activateProfile = (kind: "embedding" | "reranker", profile: any) => {
    setState({
      ...state,
      runtimeSettings: {
        ...state.runtimeSettings,
        retrieval_models: { ...models, [kind]: { ...profile, status: "configured" } },
      },
    });
    setMessage(`${kind === "embedding" ? "Embedding" : "Rerank"} 档案已设为当前，点击保存配置后应用`);
  };
  return (
    <section className="space-y-4">
      <SectionHeading
        icon={<Bot className="h-4 w-4" />}
        title={inlineUiText("检索与判断模型")}
        description={inlineUiText("统一管理 Embedding、Rerank、融合算法，以及可选的 JEV 判断服务。")}
        message={message}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <ModelCard
          title={inlineUiText("向量模型（Embedding）")}
          model={models.embedding}
          update={(f: string, v: any) => update("embedding", f, v)}
          fields={["model", "local_path", "dimensions", "device"]}
        />
        <ModelCard
          title={inlineUiText("重排模型（Rerank）")}
          model={models.reranker}
          update={(f: string, v: any) => update("reranker", f, v)}
          fields={["model", "local_path", "device"]}
        />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        {(["embedding", "reranker"] as const).map((kind) => {
          const key = `${kind}_profiles` as const;
          const profiles = Array.isArray(models[key]) && models[key].length ? models[key] : [models[kind]];
          return <div key={kind} className="rounded-lg border p-4">
            <div className="flex items-center justify-between gap-3">
              <div className="font-medium">{kind === "embedding" ? inlineUiText("Embedding 配置档案") : inlineUiText("Rerank 配置档案")}</div>
              <span className="text-xs text-muted-foreground">{profiles.length} 个</span>
            </div>
            <div className="mt-3 space-y-2">
              {profiles.map((profile:any) => <div key={profile.profile_id} className="flex items-center justify-between gap-2 rounded border px-3 py-2 text-xs">
                <div className="min-w-0"><div className="truncate font-mono">{profile.profile_id}</div><div className="truncate text-muted-foreground">{profile.model} · {profile.status || "configured"}</div></div>
                <div className="flex shrink-0 gap-1">
                  <button type="button" className="rounded border px-2 py-1" onClick={() => activateProfile(kind, profile)} disabled={profile.profile_id === models[kind]?.profile_id}>{inlineUiText("设为当前")}</button>
                  <button type="button" className="rounded border px-2 py-1" onClick={() => cloneProfile(kind, profile)}>{inlineUiText("复制")}</button>
                </div>
              </div>)}
            </div>
            <p className="mt-3 text-[11px] text-muted-foreground">{inlineUiText("档案保存后可在外部 RAG 页面选择；更换 Embedding 会触发索引重建提示。")}</p>
          </div>;
        })}
      </div>
      <div className="rounded-lg border p-4">
        <div className="font-medium">{inlineUiText("检索融合")}</div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span>{inlineUiText("融合算法")}</span>
            <select
              className="h-9 w-full rounded border bg-background px-2"
              value={models.fusion.algorithm}
              onChange={(e) => update("fusion", "algorithm", e.target.value)}
            >
              <option value="rrf">RRF</option>
              <option value="weighted">{inlineUiText("加权融合")}</option>
            </select>
          </label>
          <p className="self-end text-xs text-muted-foreground">
            {inlineUiText("RRF 是候选融合算法，不是 Rerank 模型。")}
          </p>
        </div>
      </div>
      <div className="rounded-lg border border-amber-200 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="font-medium">{inlineUiText("JEV 判断服务")}</div>
            <p className="mt-1 text-xs text-muted-foreground">
              {inlineUiText("用于证据审查、路由复核、故障归因和文档分类；不参与 Recall 候选检索。风险判断默认关闭。")}
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={Boolean(models.judge.enabled)}
              onChange={(e) => update("judge", "enabled", e.target.checked)}
            />
            {inlineUiText("启用")}
          </label>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <label className="space-y-1 text-xs">
            <span>{inlineUiText("运行模式")}</span>
            <select
              className="h-9 w-full rounded border bg-background px-2"
              value={models.judge.mode_policy}
              onChange={(e) => update("judge", "mode_policy", e.target.value)}
            >
              <option value="off">{inlineUiText("关闭")}</option>
              <option value="shadow">{inlineUiText("影子评估")}</option>
              <option value="assist">{inlineUiText("辅助判断")}</option>
              <option value="enforce">{inlineUiText("强制门控")}</option>
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <span>{inlineUiText("模型名称")}</span>
            <input
              className="h-9 w-full rounded border bg-background px-2"
              value={models.judge.model}
              onChange={(e) => update("judge", "model", e.target.value)}
              placeholder={inlineUiText("JEV 模型 ID")}
            />
          </label>
          <label className="space-y-1 text-xs md:col-span-2">
            <span>{inlineUiText("API 地址")}</span>
            <input
              className="h-9 w-full rounded border bg-background px-2 font-mono"
              value={models.judge.base_url}
              onChange={(e) => update("judge", "base_url", e.target.value)}
              placeholder="https://…"
            />
          </label>
          <label className="space-y-1 text-xs md:col-span-2">
            <span>{inlineUiText("JEV API Key")}</span>
            <input
              type="password"
              className="h-9 w-full rounded border bg-background px-2 font-mono"
              value={models.judge.api_key ?? ""}
              onChange={(e) => update("judge", "api_key", e.target.value)}
              placeholder={inlineUiText("留空表示保留已保存密钥")}
            />
          </label>
          <label className="flex items-center gap-2 text-xs md:col-span-2">
            <input
              type="checkbox"
              checked={Boolean(models.judge.risk_gate_enabled)}
              onChange={(e) => update("judge", "risk_gate_enabled", e.target.checked)}
            />
            {inlineUiText("启用高风险操作确认门（默认关闭）")}
          </label>
          <label className="space-y-1 text-xs md:col-span-2">
            <span>{inlineUiText("失败回退")}</span>
            <input
              readOnly
              className="h-9 w-full rounded border bg-muted px-2"
              value={inlineUiText("规则脚本 → 本地模型（如已启用） → 保守未知")}
            />
          </label>
        </div>
      </div>
      <button
        type="button"
        onClick={() => void save()}
        className="inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm text-primary-foreground"
      >
        <Save className="h-4 w-4" />
        {inlineUiText("保存配置")}
      </button>
    </section>
  );
}
function ModelCard({ title, model, update, fields }: any) {
  const choose = async () => {
    const response = await fetch("/api/evolving-profile/select-model-directory", {
      method: "POST",
    });
    const body = await response.json();
    if (body.path) update("local_path", body.path);
  };
  return (
    <div className="rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <div className="font-medium">{title}</div>
        <label className="text-xs">
          <input
            type="checkbox"
            checked={Boolean(model.enabled)}
            onChange={(e) => update("enabled", e.target.checked)}
          />{" "}
          {inlineUiText("启用")}
        </label>
      </div>
      <div className="mt-3 grid gap-3">
        <label className="space-y-1 text-xs">
          <span>{inlineUiText("来源")}</span>
          <select
            className="h-9 w-full rounded border bg-background px-2"
            value={model.mode}
            onChange={(e) => update("mode", e.target.value)}
          >
            <option value="local">{inlineUiText("本地模型")}</option>
            <option value="api">{inlineUiText("线上 API")}</option>
          </select>
        </label>
        {fields
          .filter((f: string) => f !== "local_path" || model.mode === "local")
          .map((field: string) => (
            <label className="space-y-1 text-xs" key={field}>
              <span>
                {field === "model"
                  ? inlineUiText("模型")
                  : field === "local_path"
                    ? inlineUiText("本地模型目录")
                    : field === "dimensions"
                      ? inlineUiText("向量维度")
                      : field === "device"
                        ? inlineUiText("运行设备")
                        : inlineUiText("提供商")}
              </span>
              <div className="flex gap-2">
                <input
                  className="h-9 min-w-0 flex-1 rounded border bg-background px-2 font-mono text-xs"
                  value={model[field] ?? ""}
                  onChange={(e) =>
                    update(field, field === "dimensions" ? Number(e.target.value) : e.target.value)
                  }
                />
                {field === "local_path" && (
                  <button
                    type="button"
                    className="rounded border px-3 text-xs"
                    onClick={() => void choose()}
                  >
                    {inlineUiText("选择目录")}
                  </button>
                )}
              </div>
            </label>
          ))}
        {model.mode === "api" && (
          <>
            <label className="space-y-1 text-xs">
              <span>{inlineUiText("线上 API 地址")}</span>
              <input
                className="h-9 w-full rounded border bg-background px-2 font-mono text-xs"
                value={model.base_url ?? ""}
                onChange={(e) => update("base_url", e.target.value)}
              />
            </label>
            <label className="space-y-1 text-xs">
              <span>{inlineUiText("API Key")}</span>
              <input
                type="password"
                className="h-9 w-full rounded border bg-background px-2 font-mono text-xs"
                value={model.api_key ?? ""}
                onChange={(e) => update("api_key", e.target.value)}
                placeholder={inlineUiText("留空表示保留已保存密钥")}
              />
            </label>
          </>
        )}
      </div>
    </div>
  );
}
function friendlyProviderClientError(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (/ByteString|greater than 255|character at index/i.test(message))
    return inlineUiText("连接测试失败：页面中的掩码密钥不能直接发送，请重新输入真实 API Key。");
  if (/fetch|network|timeout|timed out|aborted/i.test(message))
    return inlineUiText("连接测试失败：无法连接到 Provider，请检查地址、代理服务和端口。");
  return inlineUiText("连接测试失败：请求未完成，请稍后重试。");
}
function RuntimeOverview({ state }: { state: any }) {
  return (
    <section className="space-y-5">
      <SectionHeading
        icon={<Activity className="h-4 w-4" />}
        title={inlineUiText("运行配置概览")}
        description={`查看当前实际使用的模型、宿主和本机服务。版本 ${state.release?.product_version ?? "5.0"}`}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border p-4">
          <div className="flex items-center gap-2 font-medium">
            <Bot className="h-4 w-4" />
            {inlineUiText("后台加工模型")}
          </div>
          <dl className="mt-3 grid grid-cols-[90px_1fr] gap-y-2 text-xs">
            <dt>{inlineUiText("提供商")}</dt>
            <dd>{state.model.provider}</dd>
            <dt>{inlineUiText("模型")}</dt>
            <dd>{state.model.model}</dd>
            <dt>{inlineUiText("密钥")}</dt>
            <dd>{state.model.apiKey ?? inlineUiText("未配置")}</dd>
          </dl>
        </div>
        <div className="rounded-lg border p-4">
          <div className="flex items-center gap-2 font-medium">
            <Route className="h-4 w-4" />
            {inlineUiText("宿主接入")}
          </div>
          <p className="mt-3 text-xs">{state.hostIntegration.hosts.join(" · ")}</p>
          <p className="mt-2 text-xs text-muted-foreground">
            {inlineUiText("入口：")}{state.hostIntegration.entry} · MCP：{state.hostIntegration.mcpServer}
          </p>
        </div>
      </div>
      <div className="rounded-lg border p-4">
        <div className="mb-3 font-medium">{inlineUiText("本机服务")}</div>
        <div className="grid gap-3 md:grid-cols-3">
          {state.services.map((service: any) => (
            <div key={service.name} className="rounded border p-3 text-xs">
              <div className="flex items-center gap-2 font-medium">
                <span className={`h-2 w-2 rounded-full ${STATUS_STYLE[service.status]}`} />
                {service.name}
              </div>
              <p className="mt-2 font-mono text-[10px] text-muted-foreground">{service.url}</p>
              <p className="mt-1 text-muted-foreground">{service.detail}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
function ProviderPanel({ state }: { state: any }) {
  const [draft, setDraft] = useState(state.runtimeSettings.providers);
  useEffect(() => setDraft(state.runtimeSettings.providers), [state.runtimeSettings.providers]);
  const [message, setMessage] = useState<string | null>(null);
  const [testing, setTesting] = useState<number | "primary" | null>(null);
  const providers = [
    { key: "primary" as const, value: draft.primary ?? {} },
    ...(draft.fallbacks ?? []).map((value: any, index: number) => ({ key: index, value })),
  ];
  const update = (key: "primary" | number, field: string, value: string) => {
    if (key === "primary") setDraft({ ...draft, primary: { ...draft.primary, [field]: value } });
    else
      setDraft({
        ...draft,
        fallbacks: (draft.fallbacks ?? []).map((item: any, index: number) =>
          index === key ? { ...item, [field]: value } : item
        ),
      });
  };
  const addFallback = () =>
    setDraft({
      ...draft,
      fallbacks: [...(draft.fallbacks ?? []), { name: "", base_url: "", model: "", api_key: "" }],
    });
  const removeFallback = (index: number) =>
    setDraft({
      ...draft,
      fallbacks: (draft.fallbacks ?? []).filter((_: any, i: number) => i !== index),
    });
  const test = async (key: "primary" | number, value: any) => {
    setTesting(key);
    setMessage(null);
    try {
      const response = await fetch("/api/evolving-profile/provider-test", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(value),
      });
      const body = await response.json();
      setMessage(
        body.ok
          ? `${value.name || "Provider"} 连接正常`
          : body.error || inlineUiText("连接测试失败，请检查配置后重试。")
      );
    } catch (error) {
      setMessage(friendlyProviderClientError(error));
    } finally {
      setTesting(null);
    }
  };
  const save = async () => {
    const response = await fetch("/api/evolving-profile/runtime-settings", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...state.runtimeSettings, providers: draft }),
    });
    const body = await response.json();
    setMessage(response.ok ? inlineUiText("Provider 配置已保存") : body.error || inlineUiText("保存失败"));
  };
  return (
    <section className="space-y-4">
      <SectionHeading
        icon={<Bot className="h-4 w-4" />}
        title={inlineUiText("Provider 与 Fallback")}
        description={inlineUiText("主 Provider 失败时按顺序切换备用 Provider；API Key 只显示掩码。")}
        message={message}
      />
      {providers.map(({ key, value }) => (
        <div key={String(key)} className="rounded-lg border p-4">
          <div className="mb-3 flex items-center justify-between">
            <div className="font-medium">
              {key === "primary" ? inlineUiText("主 Provider") : `Fallback ${Number(key) + 1}`}
            </div>
            {key !== "primary" && (
              <button
                type="button"
                onClick={() => removeFallback(Number(key))}
                className="text-xs text-rose-700"
              >
                {inlineUiText("移除")}
              </button>
            )}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-xs">
              <span>{inlineUiText("提供商名称")}</span>
              <input
                className="h-9 w-full rounded border bg-background px-2"
                value={value.name ?? ""}
                onChange={(e) => update(key, "name", e.target.value)}
                placeholder={inlineUiText("OpenAI / DeepSeek / Ollama")}
              />
            </label>
            <label className="space-y-1 text-xs">
              <span>{inlineUiText("模型名称")}</span>
              <input
                className="h-9 w-full rounded border bg-background px-2"
                value={value.model ?? ""}
                onChange={(e) => update(key, "model", e.target.value)}
                placeholder={inlineUiText("模型 ID")}
              />
            </label>
            <label className="space-y-1 text-xs md:col-span-2">
              <span>{inlineUiText("Base URL")}</span>
              <input
                className="h-9 w-full rounded border bg-background px-2 font-mono"
                value={value.base_url ?? ""}
                onChange={(e) => update(key, "base_url", e.target.value)}
                placeholder="https://api.example.com/v1"
              />
            </label>
            <label className="space-y-1 text-xs">
              <span>{inlineUiText("API Key")}</span>
              <input
                type="password"
                className="h-9 w-full rounded border bg-background px-2 font-mono"
                value={value.api_key ?? ""}
                onChange={(e) => update(key, "api_key", e.target.value)}
                placeholder={inlineUiText("留空表示保留原 Key")}
              />
            </label>
            <div className="flex items-end gap-2">
              <button
                type="button"
                onClick={() => void test(key, value)}
                disabled={testing !== null}
                className="rounded border px-3 py-2 text-xs"
              >
                {testing === key ? inlineUiText("测试中…") : inlineUiText("测试连接")}
              </button>
            </div>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={addFallback} className="rounded border px-3 py-2 text-xs">
          {inlineUiText("添加 Fallback")}
        </button>
        <button
          type="button"
          onClick={() => void save()}
          className="rounded bg-primary px-4 py-2 text-xs text-primary-foreground"
        >
          {inlineUiText("保存 Provider 配置")}
        </button>
      </div>
      <p className="text-xs text-muted-foreground">
        {inlineUiText("连接测试只访问 Provider 的模型列表接口，不会发送 EP 记忆内容。")}
      </p>
    </section>
  );
}
function ScenarioPanel({ state }: { state: any }) {
  return (
    <section className="space-y-4">
      <SectionHeading
        icon={<Route className="h-4 w-4" />}
        title={inlineUiText("情景摘要")}
        description={inlineUiText("Session/Project 情境摘要、复核状态和图谱读取状态。")}
      />
      <div className="grid gap-4 md:grid-cols-3">
          <div className="rounded-lg border p-4 text-sm">{inlineUiText("Session：")}{state.context.sessionCount}</div>
        <div className="rounded-lg border p-4 text-sm">{inlineUiText("待复核：")}{state.context.pendingReview}</div>
        <div className="rounded-lg border p-4 text-sm">
          {inlineUiText("质量状态：")}{state.context.qualityStatus ?? inlineUiText("未知")}
        </div>
      </div>
      <div className="rounded-lg border p-4 text-xs text-muted-foreground">
        {inlineUiText("图谱节点")} {state.context.graph?.nodes.length ?? 0} {inlineUiText("· 关系边")}{" "}
        {state.context.graph?.edges.length ?? 0} {inlineUiText("· 时间线")}{" "}
        {state.context.graph?.timeline.length ?? 0}
      </div>
    </section>
  );
}
function BackupPanel({ state, setState, onSave, message }: any) {
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const settings = state.backup.settings || {};
  const update = (group: string, field: string, value: any) =>
    setState({
      ...state,
      backup: {
        ...state.backup,
        settings: { ...settings, [group]: { ...settings[group], [field]: value } },
      },
    });
  const handleSave = async () => {
    setSaving(true);
    setSaveState("saving");
    setSaveError(null);
    try {
      await onSave();
      setSaveState("saved");
      window.setTimeout(() => setSaveState("idle"), 2400);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : inlineUiText("备份设置保存失败"));
      setSaveState("error");
    } finally {
      setSaving(false);
    }
  };
  return (
    <section className="space-y-4">
      <SectionHeading
        icon={<HardDrive className="h-4 w-4" />}
        title={inlineUiText("备份")}
        description={inlineUiText("分别设置执行计划、保留期限和自动清理规则。")}
      />
      {saveError && <p className="text-xs text-rose-700">{saveError}</p>}
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border p-4 space-y-3">
          <div className="font-medium">{inlineUiText("执行计划")}</div>
          <label className="space-y-1 text-xs">
            <span>{inlineUiText("执行方式")}</span>
            <select
              className="h-9 w-full rounded border bg-background px-2"
              value={settings.schedule?.mode ?? "daily"}
              onChange={(e) => update("schedule", "mode", e.target.value)}
            >
              <option value="daily">{inlineUiText("每天")}</option>
              <option value="weekly">{inlineUiText("每周")}</option>
              <option value="monthly">{inlineUiText("每月")}</option>
              <option value="interval">{inlineUiText("每隔指定天数")}</option>
            </select>
          </label>
          {settings.schedule?.mode === "interval" && (
            <NumberField
              label={inlineUiText("间隔天数")}
              value={settings.schedule?.interval_days ?? 1}
              onChange={(value) => update("schedule", "interval_days", value)}
            />
          )}
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              label={inlineUiText("小时")}
              value={settings.schedule?.hour ?? 3}
              onChange={(value) => update("schedule", "hour", value)}
            />
            <NumberField
              label={inlineUiText("分钟")}
              value={settings.schedule?.minute ?? 25}
              onChange={(value) => update("schedule", "minute", value)}
            />
          </div>
        </div>
        <div className="rounded-lg border p-4 space-y-3">
          <div className="font-medium">{inlineUiText("本地保留策略")}</div>
          <label className="space-y-1 text-xs">
            <span>{inlineUiText("本地备份位置")}</span>
            <input
              className="h-9 w-full rounded border bg-background px-2 font-mono text-xs"
              value={settings.local?.root ?? ""}
              onChange={(e) => update("local", "root", e.target.value)}
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <NumberField
              label={inlineUiText("最长保留天数")}
              value={settings.local?.retention_days ?? 14}
              onChange={(value) => update("local", "retention_days", value)}
            />
            <NumberField
              label={inlineUiText("最多保留套数")}
              value={settings.local?.max_sets ?? 14}
              onChange={(value) => update("local", "max_sets", value)}
            />
          </div>
          <NumberField
            label={inlineUiText("至少保留成功备份套数")}
            value={settings.local?.min_successful_sets ?? 2}
            onChange={(value) => update("local", "min_successful_sets", value)}
          />
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={settings.local?.auto_cleanup ?? true}
              onChange={(e) => update("local", "auto_cleanup", e.target.checked)}
            />
            {inlineUiText("超过期限或数量后自动清理最旧备份")}
          </label>
        </div>
      </div>
      <div className="rounded-lg border p-4">
        <div className="font-medium">{inlineUiText("云端保留")}</div>
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <NumberField
            label={inlineUiText("最多保留云端套数")}
            value={settings.cloud?.retention_sets ?? 2}
            onChange={(value) => update("cloud", "retention_sets", value)}
          />
          <label className="flex items-end gap-2 pb-2 text-xs">
            <input
              type="checkbox"
              checked={settings.cloud?.enabled ?? true}
              onChange={(e) => update("cloud", "enabled", e.target.checked)}
            />
            {inlineUiText("启用云端镜像")}
          </label>
        </div>
      </div>
      <button
        type="button"
        onClick={() => void handleSave()}
        disabled={saving}
        className={`inline-flex items-center gap-2 rounded px-4 py-2 text-sm text-primary-foreground ${saveState === "error" ? "bg-rose-600" : saveState === "saved" ? "bg-emerald-600" : "bg-primary"}`}
      >
        {saveState === "saved" ? <CheckCircle2 className="h-4 w-4" /> : <Save className="h-4 w-4" />}
        {saving ? inlineUiText("保存中…") : saveState === "saved" ? inlineUiText("已保存") : saveState === "error" ? inlineUiText("保存失败，重试") : inlineUiText("保存备份设置")}
      </button>
    </section>
  );
}
