import { Pool } from "pg";

declare global {
  // eslint-disable-next-line no-var
  var contextViewerPool: Pool | undefined;
}

export function getPool(): Pool {
  if (!process.env.DATABASE_URL) throw new Error("Database is not configured");
  global.contextViewerPool ??= new Pool({ connectionString: process.env.DATABASE_URL, max: 5, idleTimeoutMillis: 30000 });
  return global.contextViewerPool;
}
