import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import os from "node:os";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!/^pm_[a-z_]+_[a-f0-9]{32}$/.test(id)) return NextResponse.json({ error: "过程记录 ID 无效" }, { status: 400 });
  try {
    const data = JSON.parse(await readFile(path.join(os.homedir(), ".evolving-profile/process-memory/records.json"), "utf8"));
    const rows = Array.isArray(data.records) ? data.records : [];
    const record = rows.find((r: any) => r.process_memory_id === id);
    if (!record) return NextResponse.json({ error: "过程记录不存在" }, { status: 404 });
    const ids: string[] = [...new Set<string>([...(record.derived_from || []), ...(record.source_trace_ids || [])])].slice(0, 64);
    const sources = rows.filter((r: any) => ids.includes(r.process_memory_id));
    return NextResponse.json({ record, sources, unresolved_source_ids: ids.filter(i => !sources.some((r: any) => r.process_memory_id === i)), source_role: "process_evidence_not_user_fact" });
  } catch { return NextResponse.json({ error: "过程记忆数据源不可用" }, { status: 503 }); }
}
