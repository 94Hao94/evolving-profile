import { NextRequest, NextResponse } from "next/server";

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ promptId: string }> }
) {
  const { promptId } = await context.params;
  const statusUrl = process.env.EVOLVING_PROFILE_STATUS_API_URL || "http://127.0.0.1:9998";
  const upstream = new URL(`/api/guidance/prompts/${encodeURIComponent(promptId)}`, statusUrl);
  request.nextUrl.searchParams.forEach((value, key) => upstream.searchParams.append(key, value));
  const response = await fetch(upstream, { cache: "no-store" });
  return new NextResponse(await response.text(), {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
