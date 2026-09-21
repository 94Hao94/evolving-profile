export type BackupFile = { name: string; bytes: number; modifiedMs: number };
export type CloudBackupSet = { setName: string; bytes: number; modifiedMs: number; encryptedFiles: number; plaintextFiles: number };

export function isCloudBackupSet(name: string) {
  return name.startsWith("evolving-profile-backup-") || name.startsWith("hindsight-backup-");
}

const LOCAL_PATTERN = /^(?:evolving-profile-(?:db|config|capture)-)?(\d{8}-\d{6})|^SHA256SUMS-(\d{8}-\d{6})$/;

export function summarizeLocalBackups(files: BackupFile[]) {
  const groups = new Map<string, BackupFile[]>();
  for (const file of files) {
    const match = file.name.match(LOCAL_PATTERN);
    const stamp = match?.[1] ?? match?.[2];
    if (!stamp) continue;
    groups.set(stamp, [...(groups.get(stamp) ?? []), file]);
  }
  const sets = [...groups.entries()].map(([stamp, items]) => ({
    stamp,
    bytes: items.reduce((sum, item) => sum + item.bytes, 0),
    modifiedMs: Math.max(...items.map((item) => item.modifiedMs)),
    fileCount: items.length,
    verified: items.some((item) => item.name.startsWith("SHA256SUMS-")),
    artifacts: {
      database: items.some((item) => item.name.startsWith("evolving-profile-db-")),
      config: items.some((item) => item.name.startsWith("evolving-profile-config-")),
      capture: items.some((item) => item.name.startsWith("evolving-profile-capture-")),
    },
  })).sort((a, b) => b.modifiedMs - a.modifiedMs);
  const latest = sets[0];
  return {
    status: latest ? "healthy" as const : "missing" as const,
    setCount: sets.length,
    fileCount: sets.reduce((sum, item) => sum + item.fileCount, 0),
    totalBytes: sets.reduce((sum, item) => sum + item.bytes, 0),
    latestSet: latest?.stamp ?? null,
    latestAt: latest ? new Date(latest.modifiedMs).toISOString() : null,
    latestBytes: latest?.bytes ?? 0,
    latestVerified: latest?.verified ?? false,
    artifacts: latest?.artifacts ?? { database: false, config: false, capture: false },
  };
}

export type CloudReadback = { observed: boolean; fileName?: string; fileId?: string; fileSize?: number; completeSize?: number; errorCode?: number; completedAt?: string | null };

export function parseCloudReadbackReceipt(value: unknown): CloudReadback {
  if (!value || typeof value !== "object") return { observed: false };
  const receipt = value as Record<string, unknown>;
  const fileName = typeof receipt.fileName === "string" ? receipt.fileName : "";
  const fileId = typeof receipt.fileId === "string" ? receipt.fileId : "";
  const fileSize = Number(receipt.fileSize);
  const completeSize = Number(receipt.completeSize);
  const errorCode = Number(receipt.errorCode);
  const completedAt = typeof receipt.completedAt === "string" && !Number.isNaN(Date.parse(receipt.completedAt))
    ? receipt.completedAt
    : null;
  const observed = receipt.observed === true
    && /^evolving-profile-backup-\d{8}-\d{6}\.zip$/i.test(fileName)
    && fileId.length > 0
    && fileSize > 0
    && completeSize === fileSize
    && errorCode === 0;
  if (!observed) return { observed: false };
  return { observed, fileName, fileId, fileSize, completeSize, errorCode, completedAt };
}

export function summarizeCloudBackups(sets: CloudBackupSet[], wpsCache: { present: boolean; fileCount: number; timedOut?: boolean }, nowMs = Date.now(), readback?: CloudReadback) {
  const ordered = [...sets].sort((a, b) => b.modifiedMs - a.modifiedMs);
  const latest = ordered[0];
  const ageHours = latest ? (nowMs - latest.modifiedMs) / 3_600_000 : null;
  const encrypted = ordered.length > 0 && ordered.every((item) => item.encryptedFiles > 0 && item.plaintextFiles === 0);
  const status = !latest ? "missing" : ageHours !== null && ageHours > 36 ? "stale" : readback?.observed ? "observed" : "unverified";
  return {
    status,
    mirrorSetCount: ordered.length,
    totalBytes: ordered.reduce((sum, item) => sum + item.bytes, 0),
    latestSet: latest?.setName ?? null,
    latestAt: latest ? new Date(latest.modifiedMs).toISOString() : null,
    ageHours: ageHours === null ? null : Math.round(ageHours * 10) / 10,
    encrypted,
    plaintextFiles: ordered.reduce((sum, item) => sum + item.plaintextFiles, 0),
    wpsCache,
    readback: readback ?? { observed: false },
  };
}
