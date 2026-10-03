import { NextResponse } from "next/server";
import { localizeApiErrorPayload } from "@/lib/i18n/api-errors";
import { sdk, lowLevelClient } from "@/lib/evolving-client";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { homedir } from "node:os";

const RELEASE_MANIFEST_PATH = path.join(process.env.EVOLVING_PROFILE_STATE_ROOT ?? path.join(homedir(), ".evolving-profile"), "config/release-manifest.json");

export async function GET(request: Request) {
  try {
    const response = await sdk.getVersion({
      client: lowLevelClient,
    });

    if (response.error) {
      console.error("API error getting version:", response.error);
      return NextResponse.json(
        localizeApiErrorPayload(request, {
          error: "Failed to get version",
          errorKey: "api.errors.version.fetch",
        }),
        { status: 500 }
      );
    }

    const data = response.data as Record<string, unknown>;
    const features = (data.features ?? {}) as Record<string, boolean>;
    features.access_key_auth = !!process.env.EVOLVING_PROFILE_ACCESS_KEY;
    data.features = features;
    try { data.evolving_profile = JSON.parse(await readFile(RELEASE_MANIFEST_PATH, "utf8")); } catch { data.evolving_profile = { product_version: "5.0", release_channel: "development", build_id: "ep5-dev" }; }

    return NextResponse.json(data, { status: 200 });
  } catch (error) {
    console.error("Error getting version:", error);
    return NextResponse.json(
      localizeApiErrorPayload(request, {
        error: "Failed to get version",
        errorKey: "api.errors.version.fetch",
      }),
      { status: 500 }
    );
  }
}
