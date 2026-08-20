import fs from "node:fs";

const files = [".env.local", ".env.test.local", "deploy/.env"].filter((file) => fs.existsSync(file));
const weakPatterns = [
  /change_me/i,
  /your[_-]?secret/i,
  /please[_-]?change/i,
  /default[_-]?secret/i,
  /secret123/i,
];

const bad = [];
for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#") || !line.includes("=")) continue;
    const [key, ...rest] = line.split("=");
    const value = rest.join("=").trim();
    if (!value) continue;
    if (/(SECRET|TOKEN|KEY|PASSWORD)/i.test(key) && weakPatterns.some((pattern) => pattern.test(value))) {
      bad.push(`${file}:${key}`);
    }
  }
}

if (bad.length > 0) {
  console.error(`[secrets] FAIL weak or default secrets: ${bad.join(", ")}`);
  process.exit(1);
}

console.log("[secrets] PASS");
