import { NextResponse } from "next/server";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export async function POST() {
  try {
    const script = 'POSIX path of (choose folder with prompt "选择本地模型目录")';
    const { stdout } = await execFileAsync("osascript", ["-e", script], { timeout: 120000 });
    const path = stdout.trim();
    if (!path) return NextResponse.json({ canceled: true });
    return NextResponse.json({ path });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    if (/User canceled|错误号 -128|(-128)/i.test(message)) return NextResponse.json({ canceled: true });
    return NextResponse.json({ error: "无法打开模型目录选择器，请手动填写本地模型目录。" }, { status: 500 });
  }
}
