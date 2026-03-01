"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPasswordSubmitting, setIsPasswordSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const callbackError = searchParams.get("error");
  const [redirectTo, setRedirectTo] = useState("");
  const [devPasswordEnabled, setDevPasswordEnabled] = useState(false);

  useEffect(() => {
    setRedirectTo(`${window.location.origin}/auth/callback`);
    if (
      process.env.NEXT_PUBLIC_ENABLE_DEV_PASSWORD_LOGIN === "true" ||
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1"
    ) {
      setDevPasswordEnabled(true);
    }
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
    <section className="w-full max-w-md rounded-2xl bg-white p-8 shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:bg-surface border border-border">
      <div className="flex flex-col items-center mb-8">
        <div className="text-accent font-bold text-3xl mb-4 tracking-tight">Pantheon</div>
        <h1 className="text-[24px] font-semibold text-foreground">Welcome to Pantheon</h1>
        <p className="mt-2 text-sm text-muted">Your AI council awaits.</p>
      </div>

      <form onSubmit={onSubmit} className="grid gap-4">
        <div className="grid gap-2">
          <input
            id="email"
            type="email"
            className="h-[48px] w-full rounded-full border-0 bg-[#F7F7F2] dark:bg-input px-6 text-foreground outline-none ring-[1px] ring-transparent focus-visible:ring-accent transition-all placeholder:text-muted"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
          />
        </div>
        <Button
          type="submit"
          disabled={isSubmitting}
          className="h-[48px] rounded-full bg-accent hover:bg-accent-hover text-white font-medium text-base transition-colors"
        >
          {isSubmitting ? "Sending..." : "Send Magic Link"}
        </Button>
      </form>

      {devPasswordEnabled ? (
        <>
          <div className="relative my-8">
            <div className="absolute inset-0 flex items-center">
              <div className="w-full border-t border-border" />
            </div>
            <div className="relative flex justify-center text-xs uppercase">
              <span className="bg-white dark:bg-surface px-2 text-muted">or</span>
            </div>
          </div>

          <form onSubmit={onPasswordSubmit} className="grid gap-4">
            <div className="grid gap-2">
              <input
                id="password"
                type="password"
                className="h-[48px] w-full rounded-full border-0 bg-[#F7F7F2] dark:bg-input px-6 text-foreground outline-none ring-[1px] ring-transparent focus-visible:ring-accent transition-all placeholder:text-muted"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Password"
                autoComplete="current-password"
              />
            </div>
            <Button
              type="submit"
              disabled={isPasswordSubmitting}
              variant="ghost"
              className="h-[48px] rounded-full border border-accent bg-transparent text-accent hover:bg-accent-subtle hover:text-accent font-medium text-base transition-colors"
              style={{ borderWidth: '2px' }}
            >
              {isPasswordSubmitting ? "Signing in..." : "Sign in with Password"}
            </Button>
          </form>
        </>
      ) : null}

      {callbackError === "callback_failed" ? (
        <p className="mt-4 text-center text-sm text-error">Magic-link callback failed. Retry sign-in.</p>
      ) : null}
      {message ? <p className="mt-4 text-center text-sm text-success">{message}</p> : null}
      {error ? <p className="mt-4 text-center text-sm text-error">{error}</p> : null}

      <div className="mt-10 flex justify-center gap-4 text-xs text-muted">
        <a href="#" className="hover:text-foreground transition-colors">Terms of Service</a>
        <a href="#" className="hover:text-foreground transition-colors">Privacy Policy</a>
      </div>
    </section>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-screen place-items-center p-4 bg-background">
      <Suspense fallback={<div className="text-muted text-sm">Loading...</div>}>
        <LoginForm />
      </Suspense>
    </main>
  );
}
