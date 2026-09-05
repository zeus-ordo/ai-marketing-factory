import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const api = await readFile("lib/api/auth.ts", "utf8");
const page = await readFile("app/members/page.tsx", "utf8");

assert.match(api, /export async function updateMemberRoles\(/);
assert.match(api, /`\/api\/v1\/companies\/\$\{companyId\}\/members\/\$\{memberId\}\/roles`/);
assert.match(api, /body: JSON\.stringify\(\{ role_ids: roleIds \}\)/);
assert.match(page, /member:assign_role/);
assert.match(page, /member:manage/);
assert.match(page, /updateMemberRoles\(user\.company_id, memberId, editingRoleIds\)/);
assert.match(page, /role\.company_id === user\?\.company_id/);
assert.match(page, /role\.is_system/);

console.log("Frontend members contract: 7 passed, 0 failed");
