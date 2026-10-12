"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/login", { method: "POST", body: JSON.stringify({ username: form.get("username"), password: form.get("password") }), headers: { "content-type": "application/json" } });
    if (response.ok) router.push("/"); else setError("Invalid credentials");
  }
  return <main style={{ maxWidth: 420, margin: "15vh auto", padding: 24 }}><h1>LLM Context Viewer</h1><form onSubmit={submit} style={{ display: "grid", gap: 12, background: "white", padding: 24, borderRadius: 12 }}><label>Username<input name="username" required style={{ display: "block", width: "100%" }} /></label><label>Password<input name="password" type="password" required style={{ display: "block", width: "100%" }} /></label>{error && <p>{error}</p>}<button>Sign in</button></form></main>;
}
