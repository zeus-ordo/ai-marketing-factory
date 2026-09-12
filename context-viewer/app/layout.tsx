import type { ReactNode } from "react";

export default function Layout({ children }: { children: ReactNode }) {
  return <html lang="en"><body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#f5f6f8", color: "#18202a" }}>{children}</body></html>;
}
