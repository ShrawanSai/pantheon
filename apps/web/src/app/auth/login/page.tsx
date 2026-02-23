"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPasswordSubmitting, setIsPasswordSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const callbackError = searchParams.get("error");
  const redirectTo = useMemo(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return `${window.location.origin}/auth/callback`;
  }, []);
  const devPasswordEnabled = useMemo(() => {
    if (process.env.NEXT_PUBLIC_ENABLE_DEV_PASSWORD_LOGIN === "true") {
      return true;
    }
    if (typeof window === "undefined") {
      return false;
    }
    return window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");

    const normalized = email.trim().toLowerCase();
    if (!normalized) {
      setError("Email is required.");
      return;
    }

    setIsSubmitting(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithOtp({
        email: normalized,
        options: {
          emailRedirectTo: redirectTo
        }
      });
      if (signInError) {
        setError(signInError.message);
      } else {
        setMessage("Magic link sent. Check your email to continue.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  async function onPasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");

    const normalized = email.trim().toLowerCase();
    if (!normalized) {
      setError("Email is required.");
      return;
    }
    if (!password) {
      setError("Password is required.");
      return;
    }

    setIsPasswordSubmitting(true);
    try {
      const supabase = getSupabaseBrowserClient();
      const { error: signInError } = await supabase.auth.signInWithPassword({
        email: normalized,
        password
      });
      if (signInError) {
        setError(signInError.message);
        return;
      }
      router.push("/rooms");
      router.refresh();
    } finally {
      setIsPasswordSubmitting(false);
    }
  }

  return (
    <main className="grid min-h-screen place-items-center p-4">
      <section className="w-full max-w-md rounded-xl border border-[--border] bg-[--bg-surface] p-6 shadow-xl">
        <h1 className="text-2xl font-semibold">Pantheon Login</h1>
        <p className="mt-2 text-sm text-[--text-muted]">Sign in with a magic link.</p>
        <form onSubmit={onSubmit} className="mt-4 grid gap-2">
          <label htmlFor="email" className="text-sm text-[--text-muted]">
            Email
          </label>
          <input
            id="email"
            type="email"
            className="h-10 w-full rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary] outline-none ring-offset-[--bg-base] placeholder:text-[--text-muted] focus-visible:ring-2 focus-visible:ring-[--accent]"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
          <Button type="submit" disabled={isSubmitting} className="mt-2">
            {isSubmitting ? "Sending..." : "Send Magic Link"}
          </Button>
        </form>
        {devPasswordEnabled ? (
          <>
            <div className="my-4 h-px bg-[--border]" />
            <p className="text-sm text-[--text-muted]">Local development: sign in with email and password.</p>
            <form onSubmit={onPasswordSubmit} className="mt-3 grid gap-2">
              <label htmlFor="password" className="text-sm text-[--text-muted]">
                Password
              </label>
              <input
                id="password"
                type="password"
                className="h-10 w-full rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary] outline-none ring-offset-[--bg-base] placeholder:text-[--text-muted] focus-visible:ring-2 focus-visible:ring-[--accent]"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Your password"
                autoComplete="current-password"
              />
              <Button type="submit" disabled={isPasswordSubmitting} className="mt-2">
                {isPasswordSubmitting ? "Signing in..." : "Sign in with Password"}
              </Button>
            </form>
          </>
        ) : null}
        {callbackError === "callback_failed" ? (
          <p className="mt-3 text-sm text-amber-300">Magic-link callback failed. Retry sign-in.</p>
        ) : null}
        {message ? <p className="mt-3 text-sm text-emerald-400">{message}</p> : null}
        {error ? <p className="mt-3 text-sm text-red-400">{error}</p> : null}
      </section>
    </main>
  );
}
