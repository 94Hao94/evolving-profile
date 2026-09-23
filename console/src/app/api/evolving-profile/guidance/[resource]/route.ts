import { NextRequest, NextResponse } from "next/server";

const RESOURCES = new Set(["units", "models", "candidates", "prompts", "memory-map", "memory-check"]);

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ resource: string }> }
) {
  const { resource } = await context.params;
  if (!RESOURCES.has(resource)) {
    return NextResponse.json({ error: "Unknown Evolving Profile guidance resource" }, { status: 404 });
  }

  const statusUrl = process.env.EVOLVING_PROFILE_STATUS_API_URL || "http://127.0.0.1:9998";
  const upstream = new URL(`/api/guidance/${resource}`, statusUrl);
  request.nextUrl.searchParams.forEach((value, key) => upstream.searchParams.append(key, value));
  const response = await fetch(upstream, { cache: "no-store" });
  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
  });
}
