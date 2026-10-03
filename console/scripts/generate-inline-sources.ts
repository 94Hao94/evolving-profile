import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";

const root = resolve(__dirname, "..");
const sources = new Set<string>();
function walk(dir: string) {
  for (const name of readdirSync(dir)) {
    if (name.startsWith(".") || name === "node_modules") continue;
    const full = join(dir, name);
    if (statSync(full).isDirectory()) walk(full);
    else if (name.endsWith(".tsx")) {
      const text = readFileSync(full, "utf8");
      for (const match of text.matchAll(/(["'`])([^"'`]*[\u3400-\u9fff][^"'`]*)\1/g)) sources.add(match[2]);
    }
  }
}
walk(join(root, "src/components"));
walk(join(root, "src/app"));
const output = `// Generated from static UI literals. Do not put user data here.\nexport const INLINE_STATIC_SOURCES = new Set<string>(${JSON.stringify([...sources].sort(), null, 2)});\n`;
writeFileSync(join(root, "src/lib/inline-sources.generated.ts"), output);
console.log(`generated ${sources.size} static UI sources`);
