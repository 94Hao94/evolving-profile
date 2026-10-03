import { readFileSync, writeFileSync } from "node:fs";
import ts from "typescript";

const files = process.argv.slice(2);
for (const file of files) {
  const source = readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits: Array<{ start: number; end: number; text: string }> = [];
  const hasCjk = (s: string) => /[\u3400-\u9fff]/u.test(s);
  function visit(node: ts.Node) {
    if (ts.isStringLiteral(node) && hasCjk(node.text)) {
      const parent = node.parent;
      const isPropertyName = (ts.isPropertyAssignment(parent) && parent.name === node) ||
        (ts.isMethodDeclaration(parent) && parent.name === node) ||
        (ts.isElementAccessExpression(parent) && parent.argumentExpression === node);
      const isImportPath = ts.isImportDeclaration(parent) || ts.isExportDeclaration(parent);
      const isAlreadyLocalized = ts.isCallExpression(parent) && ts.isIdentifier(parent.expression) && parent.expression.text === "inlineUiText";
      if (!isPropertyName && !isImportPath && !isAlreadyLocalized) {
        edits.push({ start: node.getStart(sf), end: node.getEnd(), text: `inlineUiText(${JSON.stringify(node.text)})` });
      }
    }
    ts.forEachChild(node, visit);
  }
  visit(sf);
  let out = source;
  for (const edit of edits.sort((a, b) => b.start - a.start)) out = out.slice(0, edit.start) + edit.text + out.slice(edit.end);
  if (edits.length && !out.includes('from "@/lib/inline-i18n"')) {
    const match = out.match(/^((?:import[^;]+;\s*)+)/m);
    const line = 'import { inlineUiText } from "@/lib/inline-i18n";\n';
    out = match ? out.slice(0, match.index! + match[0].length) + line + out.slice(match.index! + match[0].length) : line + out;
  }
  if (edits.length) { writeFileSync(file, out); console.log(file, edits.length); }
}
