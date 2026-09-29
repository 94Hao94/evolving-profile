export function resolveConsoleOrigin(requestUrl: string, configuredPort?: string) {
  const url = new URL(requestUrl);
  const port = configuredPort?.trim() || url.port || "9999";
  return `${url.protocol}//${url.hostname}:${port}`;
}
