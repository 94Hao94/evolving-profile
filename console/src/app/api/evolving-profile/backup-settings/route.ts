import { NextResponse } from "next/server";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { randomUUID } from "node:crypto";
import path from "node:path";
import { homedir } from "node:os";

const EP_ROOT = process.env.EVOLVING_PROFILE_STATE_ROOT ?? path.join(process.env.HOME ?? homedir(), ".evolving-profile");
const SETTINGS_PATH = path.join(EP_ROOT, "config/backup-settings.json");
const PLIST_PATH = path.join(process.env.HOME ?? homedir(), "Library/LaunchAgents/com.evolving-profile.backup.plist");
const execFileAsync = promisify(execFile);

const defaults = {
  schema: "evolving-profile.backup-settings.v1",
  enabled: true,
  schedule: { mode: "daily", hour: 3, minute: 25, weekday: 1, day: 1, interval_days: 1 },
  local: { root: path.join(EP_ROOT, "backups/managed"), retention_days: 14, max_sets: 14, min_successful_sets: 2, auto_cleanup: true, database: true, config: true, capture: true, verify_checksum: true },
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
  if (!['daily', 'weekly', 'monthly', 'interval'].includes(mode)) throw new Error("invalid_schedule_mode");
  if (mode === "interval" && (!Number.isInteger(value.schedule?.interval_days) || value.schedule.interval_days < 1 || value.schedule.interval_days > 365)) throw new Error("invalid_interval_days");
  for (const key of ['hour', 'minute']) if (!Number.isInteger(value.schedule[key]) || value.schedule[key] < 0 || (key === 'hour' ? value.schedule[key] > 23 : value.schedule[key] > 59)) throw new Error("invalid_schedule_time");
  if (mode === "weekly" && (!Number.isInteger(value.schedule.weekday) || value.schedule.weekday < 0 || value.schedule.weekday > 6)) throw new Error("invalid_schedule_weekday");
  if (mode === "monthly" && (!Number.isInteger(value.schedule.day) || value.schedule.day < 1 || value.schedule.day > 28)) throw new Error("invalid_schedule_day");
  if (!Number.isInteger(value.local?.retention_days) || value.local.retention_days < 1 || value.local.retention_days > 3650) throw new Error("invalid_retention_days");
  if (!Number.isInteger(value.local?.max_sets) || value.local.max_sets < 1 || value.local.max_sets > 1000) throw new Error("invalid_max_sets");
  if (!Number.isInteger(value.local?.min_successful_sets) || value.local.min_successful_sets < 1 || value.local.min_successful_sets > value.local.max_sets) throw new Error("invalid_min_successful_sets");
  if (typeof value.local?.auto_cleanup !== "boolean") throw new Error("invalid_auto_cleanup");
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
    await mkdir(path.dirname(SETTINGS_PATH), { recursive: true });
    await writeFile(SETTINGS_PATH, JSON.stringify(settings, null, 2) + "\n", { mode: 0o600 });
    const plistUpdater = [
      "import json, os, plistlib, sys, uuid",
      "from pathlib import Path",
      "path=Path(sys.argv[1]); config=json.loads(sys.argv[2]); data=plistlib.loads(path.read_bytes())",
      "schedule=config['schedule']; mode=schedule['mode']; hour=int(schedule['hour']); minute=int(schedule['minute'])",
      "args=data.get('ProgramArguments', [])",
      "if len(args)>1: args[1]=mode",
      "data['ProgramArguments']=args",
      "data.pop('StartInterval', None)",
      "if mode=='interval': mode='daily'",
      "calendar={'Hour':hour,'Minute':minute}",
      "if mode=='weekly': calendar['Weekday']=int(schedule['weekday'])",
      "if mode=='monthly': calendar['Day']=int(schedule['day'])",
      "data['StartCalendarInterval']=calendar",
      "temporary=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')",
      "temporary.write_bytes(plistlib.dumps(data, fmt=plistlib.FMT_XML, sort_keys=False)); os.chmod(temporary, 0o600); os.replace(temporary,path)",
    ].join("\n");
    await execFileAsync(process.env.EP_RUNTIME_PYTHON ?? "python3", ["-c", plistUpdater, PLIST_PATH, JSON.stringify(settings)], { timeout: 10000 });
    await execFileAsync("launchctl", ["bootout", `gui/${process.getuid?.() ?? 501}/com.evolving-profile.backup`]).catch(() => undefined);
    if (settings.enabled) await execFileAsync("launchctl", ["bootstrap", `gui/${process.getuid?.() ?? 501}`, PLIST_PATH]);
    return NextResponse.json({ ...settings, applied: true });
  } catch (error) {
    return NextResponse.json({ error: error instanceof Error ? error.message : "backup_settings_failed" }, { status: 400 });
  }
}
