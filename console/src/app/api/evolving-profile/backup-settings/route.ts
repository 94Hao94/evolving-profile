import { NextResponse } from "next/server";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { homedir } from "node:os";
import path from "node:path";

const HOME = process.env.HOME ?? homedir();
const STATE_ROOT = process.env.EVOLVING_PROFILE_STATE_ROOT ?? path.join(HOME, ".evolving-profile");
const SETTINGS_PATH = path.join(STATE_ROOT, "config/backup-settings.json");
const PLIST_PATH = path.join(HOME, "Library/LaunchAgents/com.evolving-profile.backup.plist");
const execFileAsync = promisify(execFile);

const defaults = {
  schema: "evolving-profile.backup-settings.v1",
  enabled: true,
  schedule: { mode: "daily", hour: 3, minute: 25, weekday: 1, day: 1 },
  local: { root: path.join(STATE_ROOT, "backups/managed"), retention_days: 14, max_sets: 14, database: true, config: true, capture: true, verify_checksum: true },
  cloud: { enabled: true, provider: "WPS mirror", retention_sets: 2, encryption: "AES-256-CBC + PBKDF2-SHA256" },
};

async function readSettings() {
  try {
    const stored = JSON.parse(await readFile(SETTINGS_PATH, "utf8"));
    return { ...defaults, ...stored, schedule: { ...defaults.schedule, ...stored.schedule }, local: { ...defaults.local, ...stored.local }, cloud: { ...defaults.cloud, ...stored.cloud } };
  }
  catch { return defaults; }
}

function validate(value: any) {
  if (!value || typeof value !== "object") throw new Error("invalid_settings");
  const mode = value.schedule?.mode;
  if (!['daily', 'weekly', 'monthly'].includes(mode)) throw new Error("invalid_schedule_mode");
  for (const key of ['hour', 'minute']) if (!Number.isInteger(value.schedule[key]) || value.schedule[key] < 0 || (key === 'hour' ? value.schedule[key] > 23 : value.schedule[key] > 59)) throw new Error("invalid_schedule_time");
  if (mode === "weekly" && (!Number.isInteger(value.schedule.weekday) || value.schedule.weekday < 0 || value.schedule.weekday > 6)) throw new Error("invalid_schedule_weekday");
  if (mode === "monthly" && (!Number.isInteger(value.schedule.day) || value.schedule.day < 1 || value.schedule.day > 28)) throw new Error("invalid_schedule_day");
  if (!Number.isInteger(value.local?.retention_days) || value.local.retention_days < 1 || value.local.retention_days > 3650) throw new Error("invalid_retention_days");
  if (!Number.isInteger(value.local?.max_sets) || value.local.max_sets < 1 || value.local.max_sets > 1000) throw new Error("invalid_max_sets");
  const root = String(value.local?.root ?? "");
  if (!root.startsWith("/") || root.includes("..") || root === "/" || root === "/Users" || root === "/Library" || root === "/System") throw new Error("invalid_backup_root");
  if (!["database", "config", "capture", "verify_checksum"].every((key) => typeof value.local?.[key] === "boolean")) throw new Error("invalid_backup_artifacts");
  if (![value.local.database, value.local.config, value.local.capture].some(Boolean)) throw new Error("no_backup_artifacts");
  if (!Number.isInteger(value.cloud?.retention_sets) || value.cloud.retention_sets < 0 || value.cloud.retention_sets > 1000) throw new Error("invalid_cloud_retention");
}

export async function GET() { return NextResponse.json(await readSettings()); }

export async function POST(request: Request) {
  try {
    const incoming = await request.json();
    const settings = { ...defaults, ...incoming, schedule: { ...defaults.schedule, ...incoming.schedule }, local: { ...defaults.local, ...incoming.local }, cloud: { ...defaults.cloud, ...incoming.cloud }, updated_at: new Date().toISOString() };
    validate(settings);
    await mkdir(path.join(STATE_ROOT, "config"), { recursive: true });
    await writeFile(SETTINGS_PATH, JSON.stringify(settings, null, 2) + "\n", { mode: 0o600 });
    const hour = Number(settings.schedule.hour), minute = Number(settings.schedule.minute);
    const plist = await readFile(PLIST_PATH, "utf8");
    const mode = String(settings.schedule.mode);
    const calendar = mode === "weekly"
      ? `<dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${minute}</integer><key>Weekday</key><integer>${settings.schedule.weekday}</integer></dict>`
      : mode === "monthly"
        ? `<dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${minute}</integer><key>Day</key><integer>${settings.schedule.day}</integer></dict>`
        : `<dict><key>Hour</key><integer>${hour}</integer><key>Minute</key><integer>${minute}</integer></dict>`;
    const updated = plist
      .replace(/(<key>Hour<\/key><integer>)[0-9]+(<\/integer>)/, `$1${hour}$2`)
      .replace(/(<key>Minute<\/key><integer>)[0-9]+(<\/integer>)/, `$1${minute}$2`)
      .replace(/(<key>StartCalendarInterval<\/key>)<dict>[\s\S]*?<\/dict>/, `$1${calendar}`)
      .replace(/(<key>ProgramArguments<\/key><array><string>[^<]+<\/string><string>)(daily|weekly|monthly)(<\/string>)/, `$1${mode}$3`);
    await writeFile(PLIST_PATH, updated, { mode: 0o600 });
    await execFileAsync("launchctl", ["bootout", `gui/${process.getuid?.() ?? 501}/com.evolving-profile.backup`]).catch(() => undefined);
    await execFileAsync("launchctl", ["bootstrap", `gui/${process.getuid?.() ?? 501}`, PLIST_PATH]);
    return NextResponse.json({ ...settings, applied: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "backup_settings_failed" }, { status: 400 });
  }
}
