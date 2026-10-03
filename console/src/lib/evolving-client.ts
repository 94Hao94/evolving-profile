/**
 * Shared Evolving Profile API client instance for the control plane.
 * Configured to connect to the dataplane API server.
 */

import {
  EvolvingProfileClient,
  EvolvingProfileError,
  createClient,
  createConfig,
  sdk,
} from "@evolving-profile/client";

// EP5.0's local shadow data plane is the service that owns the live bank API.
// Keep the environment override for packaged deployments, but do not fall
// back to the retired 8888 control-plane port on a fresh local install.
export const DATAPLANE_URL = process.env.EVOLVING_PROFILE_DATAPLANE_API_URL || "http://127.0.0.1:12088";
const DATAPLANE_API_KEY = process.env.EVOLVING_PROFILE_DATAPLANE_API_KEY || "";

/**
 * Auth headers for direct fetch calls to the dataplane API.
 */
export function getDataplaneHeaders(extra?: Record<string, string>): Record<string, string> {
  const headers: Record<string, string> = { ...extra };
  if (DATAPLANE_API_KEY) {
    headers["Authorization"] = `Bearer ${DATAPLANE_API_KEY}`;
  }
  return headers;
}

/**
 * Build a dataplane URL for a bank-scoped endpoint with the bank id properly encoded.
 * Bank ids may contain `:`, `/`, `%`, etc. (e.g. openclaw `agent::channel::user`),
 * which must be percent-encoded before being interpolated into a URL path.
 */
export function dataplaneBankUrl(bankId: string, suffix = ""): string {
  return `${DATAPLANE_URL}/v1/default/banks/${encodeURIComponent(bankId)}${suffix}`;
}

/**
 * High-level client with convenience methods
 */
export const evolvingProfileClient = new EvolvingProfileClient({
  baseUrl: DATAPLANE_URL,
  apiKey: DATAPLANE_API_KEY || undefined,
});

/**
 * Low-level client for direct SDK access
 */
export const lowLevelClient = createClient(
  createConfig({
    baseUrl: DATAPLANE_URL,
    headers: DATAPLANE_API_KEY ? { Authorization: `Bearer ${DATAPLANE_API_KEY}` } : undefined,
  })
);

/**
 * Export SDK functions for direct API access
 */
export { sdk };

/**
 * Export EvolvingProfileError for error handling
 */
export { EvolvingProfileError };
