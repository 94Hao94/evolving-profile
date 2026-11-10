import { NextResponse } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

function registryPath() {
  const sourceRoot = process.env.EVOLVING_PROFILE_HOST_SOURCE_ROOT ?? path.resolve(process.cwd(), "..");
  return path.join(sourceRoot, "config", "host-integrations.v1.json");
}

export async function GET() {
  try {
    const registry = JSON.parse(await readFile(registryPath(), "utf8"));
    const profiles = Array.isArray(registry?.profiles)
      ? registry.profiles.map((profile: any) => ({
          id: String(profile.id),
          labels: profile.labels ?? { en: String(profile.id), "zh-CN": String(profile.id) },
          documented: profile.documented ?? {},
          platforms: profile.platforms ?? [],
          transports: profile.transports ?? [],
          source_parser: profile.source_parser ?? null,
        }))
      : [];
    return NextResponse.json(
      { schema: "ep.host-catalog.v1", revision: registry?.revision ?? null, profiles },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch {
    return NextResponse.json(
      { schema: "ep.host-catalog.v1", revision: null, profiles: [] },
      { headers: { "Cache-Control": "no-store" } },
    );
  }
}
