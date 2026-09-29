import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { access, stat } from "node:fs/promises";

const execFileAsync = promisify(execFile);

export async function POST() {
  if (process.platform !== "darwin") {
    return NextResponse.json({ error: "directory_picker_unavailable_on_this_platform" }, { status: 501 });
  }
  try {
    const script = 'POSIX path of (choose folder with prompt "选择外部 RAG 资料目录")';
    const { stdout } = await execFileAsync("osascript", ["-e", script], { timeout: 120000 });
    const directory = stdout.trim();
    const info = await stat(directory);
    await access(directory);
    if (!info.isDirectory()) throw new Error("selected_path_is_not_directory");
    return NextResponse.json({ path: directory, readable: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/User canceled|ユーザがキャンセル|操作がキャンセル/i.test(message)) {
      return NextResponse.json({ canceled: true });
    }
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
