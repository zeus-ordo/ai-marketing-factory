export const REVIEW_PERMISSIONS = [
  "review:manage",
  "review:approve",
  "review:reject",
  "review:revision",
] as const;

export function hasPermission(permissions: string[], permission: string) {
  return permissions.some((value) => ["*", "admin", "platform:admin", permission].includes(value));
}

export function canReview(permissions: string[]) {
  return REVIEW_PERMISSIONS.some((permission) => hasPermission(permissions, permission));
}
