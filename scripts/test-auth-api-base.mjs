import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../lib/api/auth.ts", import.meta.url), "utf8");

if (!source.includes('?? "/"') || !source.includes(': "/"')) {
  throw new Error("Browser auth API fallback must use same-origin /, not localhost");
}

if (source.includes("localhost:8095")) {
  throw new Error("Browser auth API must not fall back to localhost:8095");
}

console.log("auth API base fallback test passed");
