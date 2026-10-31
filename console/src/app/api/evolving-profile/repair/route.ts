import { NextRequest, NextResponse } from "next/server";
import { dataplaneBankUrl, getDataplaneHeaders } from "@/lib/evolving-client";

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const bankId = typeof body?.bankId === "string" ? body.bankId : "";
  const action = body?.action === "apply" ? "apply" : body?.action === "cancel" ? "cancel" : "diagnose";
  const repairId = typeof body?.repairId === "string" ? body.repairId : "";
  if (!bankId) return NextResponse.json({ detail: "bank_id_required" }, { status: 400 });
  const path = (action === "apply" || action === "cancel") && repairId
    ? `/repairs/${encodeURIComponent(repairId)}/${action}`
    : "/repairs/diagnose";
  const upstream = await fetch(dataplaneBankUrl(bankId, path), {
    method: "POST",
    headers: { ...getDataplaneHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify(action === "apply" ? body?.payload ?? {} : body?.payload ?? {}),
    cache: "no-store",
    signal: AbortSignal.timeout(180000),
  }).catch((error) => NextResponse.json({ detail: String(error) }, { status: 502 }));
  if (upstream instanceof NextResponse) return upstream;
  const payload = await upstream.json().catch(() => ({ detail: "invalid_repair_response" }));
  return NextResponse.json(payload, { status: upstream.status });
}

export async function GET(request: NextRequest) {
  const bankId = request.nextUrl.searchParams.get("bankId") || "";
  const repairId = request.nextUrl.searchParams.get("repairId") || "";
  if (!bankId || !repairId) return NextResponse.json({ detail: "bank_id_and_repair_id_required" }, { status: 400 });
  const upstream = await fetch(dataplaneBankUrl(bankId, `/repairs/${encodeURIComponent(repairId)}`), { headers: getDataplaneHeaders(), cache: "no-store", signal: AbortSignal.timeout(10000) });
  const payload = await upstream.json().catch(() => ({ detail: "invalid_repair_response" }));
  return NextResponse.json(payload, { status: upstream.status });
}
