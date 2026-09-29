import { describe, expect, it } from "vitest";
import { summarizeLocalBackups, summarizeCloudBackups, isCloudBackupSet, parseCloudReadbackReceipt } from "@/lib/backup-status";

describe("backup status summaries", () => {
  it("recognizes current EP cloud sets while keeping legacy sets readable", () => {
    expect(isCloudBackupSet("evolving-profile-backup-20260920-032504")).toBe(true);
    expect(isCloudBackupSet("hindsight-backup-20260916-031005")).toBe(true);
    expect(isCloudBackupSet("random-folder")).toBe(false);
  });
  it("groups one local backup set and totals its actual artifacts", () => {
    const result = summarizeLocalBackups([
      { name: "evolving-profile-db-20260919-032508.dump", bytes: 700, modifiedMs: 3000 },
      { name: "evolving-profile-config-20260919-032508.tar.gz.enc", bytes: 20, modifiedMs: 3010 },
      { name: "evolving-profile-capture-20260919-032508.sqlite.gz.enc", bytes: 10, modifiedMs: 3020 },
      { name: "SHA256SUMS-20260919-032508", bytes: 1, modifiedMs: 3030 },
      { name: "unrelated.txt", bytes: 999, modifiedMs: 9000 },
    ]);

    expect(result).toMatchObject({ setCount: 1, fileCount: 4, totalBytes: 731, latestSet: "20260919-032508", latestBytes: 731, latestVerified: true });
  });

  it("reports a stale cloud mirror separately from an empty WPS cache", () => {
    const result = summarizeCloudBackups(
      [{ setName: "hindsight-backup-20260916-031005", bytes: 800, modifiedMs: 1000, encryptedFiles: 2, plaintextFiles: 0 }],
      { present: true, fileCount: 0 },
      Date.parse("2026-09-19T12:00:00+08:00"),
      { observed: true, fileId: "cloud-1", fileSize: 800, completeSize: 800, errorCode: 0 },
    );

    expect(result.status).toBe("stale");
    expect(result.mirrorSetCount).toBe(1);
    expect(result.encrypted).toBe(true);
    expect(result.wpsCache).toEqual({ present: true, fileCount: 0 });
  });

  it("requires WPS cloud readback instead of treating a local cache file as synced", () => {
    const set = [{ setName: "evolving-profile-backup-20260920-032504", bytes: 1500, modifiedMs: Date.parse("2026-09-20T03:25:00+08:00"), encryptedFiles: 3, plaintextFiles: 0 }];
    expect(summarizeCloudBackups(set, { present: true, fileCount: 5 }, Date.parse("2026-09-20T11:00:00+08:00")).status).toBe("unverified");
    const verified = summarizeCloudBackups(set, { present: true, fileCount: 5 }, Date.parse("2026-09-20T11:00:00+08:00"), { observed: true, fileId: "565532104620", fileSize: 1500, completeSize: 1500, errorCode: 0 });
    expect(verified.status).toBe("observed");
  });

  it("keeps a timed-out WPS cache distinct from an observed empty cache", () => {
    const result = summarizeCloudBackups([], { present: true, fileCount: 0, timedOut: true }, Date.now());
    expect(result.status).toBe("missing");
    expect(result.wpsCache.timedOut).toBe(true);
  });

  it("accepts only a complete successful WPS upload receipt", () => {
    expect(parseCloudReadbackReceipt({
      observed: true,
      fileName: "evolving-profile-backup-20260920-032504.zip",
      fileId: "565532104620",
      fileSize: 1577187069,
      completeSize: 1577187069,
      errorCode: 0,
      completedAt: "2026-09-20T03:25:38.685Z",
    })).toMatchObject({ observed: true, fileId: "565532104620" });

    expect(parseCloudReadbackReceipt({
      observed: true,
      fileName: "evolving-profile-backup-20260920-032504.zip",
      fileId: "565532104620",
      fileSize: 1577187069,
      completeSize: 120,
      errorCode: 0,
    })).toEqual({ observed: false });
  });
});
