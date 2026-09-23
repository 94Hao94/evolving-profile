import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest, context: { params: Promise<{ topicId: string }> }) {
  const { topicId } = await context.params;
  const base = process.env.EVOLVING_PROFILE_STATUS_API_URL || "http://127.0.0.1:12098";
  const upstream = new URL(`/api/guidance/topics/${encodeURIComponent(topicId)}`, base);
  upstream.searchParams.set("offset", request.nextUrl.searchParams.get("offset") || "0");
  try {
    const response = await fetch(upstream, { cache: "no-store", signal: AbortSignal.timeout(5000) });
    return new NextResponse(await response.text(), { status: response.status, headers: { "Content-Type": "application/json" } });
  } catch {
    return NextResponse.json({ error: "目录暂时不可读" }, { status: 503 });
  }
}
