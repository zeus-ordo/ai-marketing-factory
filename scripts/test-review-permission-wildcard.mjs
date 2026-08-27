import { readFile } from "node:fs/promises";

const sideNav = await readFile(new URL("../components/layout/side-nav-bar.tsx", import.meta.url), "utf8");
const reviewPage = await readFile(new URL("../app/review/page.tsx", import.meta.url), "utf8");

if (!sideNav.includes('["*", "admin", "platform:admin"')) {
  throw new Error("Review navigation must recognize wildcard permissions");
}

if (!reviewPage.includes('["*", "admin", "platform:admin"')) {
  throw new Error("Review page must recognize wildcard permissions");
}

console.log("review wildcard permission test passed");
