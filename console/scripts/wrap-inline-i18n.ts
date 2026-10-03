import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import ts from "typescript";

const ROOT = resolve(__dirname, "..");
const targets = ["src/components", "src/app"];
const files: string[] = [];

function walk(dir: string) {
  for (const name of readdirSync(dir)) {
    if (name.startsWith(".") || name === "node_modules") continue;
    const full = join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) walk(full);
    else if (name.endsWith(".tsx")) files.push(full);
  }
}
for (const target of targets) walk(resolve(ROOT, target));

function hasCjk(value: string) { return /[\u3400-\u9fff]/u.test(value); }
function literal(value: string) { return `inlineUiText(${JSON.stringify(value)})`; }

for (const file of files) {
  const source = readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits: Array<{ start: number; end: number; text: string }> = [];
  function visit(node: ts.Node) {
    if (ts.isJsxText(node)) {
      const raw = node.getText(sf);
      const trimmed = raw.replace(/\s+/g, " ").trim();
      if (hasCjk(trimmed) && trimmed.length > 1) {
        const leading = raw.slice(0, raw.indexOf(trimmed));
        const trailing = raw.slice(raw.indexOf(trimmed) + trimmed.length);
        edits.push({ start: node.getStart(sf), end: node.getEnd(), text: `${leading}{${literal(trimmed)}}${trailing}` });
      }
    }
    if (ts.isJsxAttribute(node) && node.initializer && ts.isStringLiteral(node.initializer) && hasCjk(node.initializer.text)) {
      edits.push({ start: node.initializer.getStart(sf), end: node.initializer.getEnd(), text: `{${literal(node.initializer.text)}}` });
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);
  if (!edits.length) continue;
  let out = source;
  for (const edit of edits.sort((a, b) => b.start - a.start)) out = out.slice(0, edit.start) + edit.text + out.slice(edit.end);
  if (!out.includes('from "@/lib/inline-i18n"')) {
    const importMatch = out.match(/^((?:import[^;]+;\s*)+)/m);
    const importLine = 'import { inlineUiText } from "@/lib/inline-i18n";\n';
    out = importMatch ? out.slice(0, importMatch.index! + importMatch[0].length) + importLine + out.slice(importMatch.index! + importMatch[0].length) : importLine + out;
  }
  writeFileSync(file, out);
  console.log(file.replace(ROOT + "/", ""), edits.length);
}
