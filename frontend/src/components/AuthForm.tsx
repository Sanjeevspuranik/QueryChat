"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { api } from "@/lib/api";
import ThemeToggle from "./ThemeToggle";

export default function AuthForm({ mode }: { mode: "login" | "register" }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isLogin = mode === "login";

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await (isLogin ? api.login : api.register)(email, password);
      router.replace("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to continue.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <div className="theme-corner"><ThemeToggle /></div>
      <form onSubmit={submit} className="card">
        <h1>📊 QueryChat</h1>
        <p className="muted">{isLogin ? "Sign in to continue" : "Create your account"}</p>
        <label>
          Email
          <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </label>
        <label>
          Password
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={isLogin ? "current-password" : "new-password"}
          />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button disabled={busy}>{busy ? "Please wait…" : isLogin ? "Sign in" : "Sign up"}</button>
        <p className="muted">
          {isLogin ? <Link href="/register">Create an account</Link> : <Link href="/login">Already registered? Sign in</Link>}
        </p>
      </form>
    </main>
  );
}
