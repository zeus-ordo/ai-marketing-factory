import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const STORE_PATH = join(process.cwd(), ".data", "content-folders.json");

export function getFolders(): string[] {
  try {
    const raw = readFileSync(STORE_PATH, "utf8");
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
  } catch {
    return [];
  }
}

export function saveFolders(folders: string[]): void {
  const unique = Array.from(new Set(folders.map((name) => name.trim()).filter(Boolean))).sort();
  mkdirSync(dirname(STORE_PATH), { recursive: true });
  writeFileSync(STORE_PATH, JSON.stringify(unique, null, 2), "utf8");
}
