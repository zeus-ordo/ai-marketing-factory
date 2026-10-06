import { readFile } from "node:fs/promises";
import ts from "typescript";

const source = await readFile(new URL("../lib/auth/permissions.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const permissions = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);

for (const permission of ["platform:admin", "admin", "*"]) {
  if (!permissions.isPlatformAdmin([permission])) {
    throw new Error(`${permission} must be recognized as a platform admin`);
  }
}

if (permissions.isPlatformAdmin(["reference:read"])) {
  throw new Error("company permissions must not be recognized as platform admin");
}

console.log("platform-admin permission contract test passed");
