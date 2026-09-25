import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const helper = await readFile("lib/auth/permissions.ts", "utf8");
const reviewPage = await readFile("app/review/page.tsx", "utf8");
const sideNav = await readFile("components/layout/side-nav-bar.tsx", "utf8");

test("shared frontend helper recognizes review:manage and bypasses", () => {
  assert.match(helper, /"review:manage"/);
  assert.match(helper, /"\*", "admin", "platform:admin"/);
});

test("Review page and side navigation use the shared helper", () => {
  assert.match(reviewPage, /from "@\/lib\/auth\/permissions"/);
  assert.match(reviewPage, /hasReviewPermission\(user\.permissions\)/);
  assert.match(sideNav, /from "@\/lib\/auth\/permissions"/);
  assert.match(sideNav, /return canReview\(permissions\)/);
  assert.doesNotMatch(reviewPage, /manager|admin.*role|role.*admin/i);
  assert.doesNotMatch(sideNav, /manager|admin.*role|role.*admin/i);
});
