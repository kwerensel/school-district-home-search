import { useCallback, useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useServerFn } from "@tanstack/react-start";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { authClient } from "@/lib/auth-client";
import { getPublicAuthConfig } from "@/lib/auth-config.functions";
import { safeReturnTo } from "@/lib/auth-navigation";
import { TurnstileWidget } from "./TurnstileWidget";

export function AuthCard({ mode }: { mode: "login" | "signup" }) {
  const getConfig = useServerFn(getPublicAuthConfig);
  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["public-auth-config"], queryFn: () => getConfig() });
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [turnstileToken, setTurnstileToken] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const onToken = useCallback((token: string) => setTurnstileToken(token), []);
  const returnTo = safeReturnTo(
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("returnTo"),
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      const result =
        mode === "signup"
          ? await authClient.signUp.email({
              name,
              email,
              password,
              fetchOptions: { headers: { "x-turnstile-token": turnstileToken } },
            })
          : await authClient.signIn.email({ email, password });
      if (result.error) throw new Error(result.error.message || "Authentication failed");
      await queryClient.invalidateQueries({ queryKey: ["auth-session"] });
      window.location.assign(returnTo);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Authentication failed");
    } finally {
      setPending(false);
    }
  }

  const signupReady = mode === "login" || Boolean(turnstileToken);
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-4">
      <section className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-foreground">
          {mode === "signup" ? "Create your optional account" : "Sign in to Groundtruth"}
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Accounts save searches and favorites. Discovery and Explorer always work without one.
        </p>
        <form className="mt-6 space-y-4" onSubmit={submit}>
          {mode === "signup" ? (
            <div className="space-y-2">
              <Label htmlFor="auth-name">Name</Label>
              <Input
                id="auth-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                maxLength={120}
              />
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="auth-email">Email</Label>
            <Input
              id="auth-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="auth-password">Password</Label>
            <Input
              id="auth-password"
              type="password"
              autoComplete={mode === "signup" ? "new-password" : "current-password"}
              minLength={10}
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </div>
          {mode === "signup" ? (
            config.data?.turnstileSiteKey ? (
              <TurnstileWidget siteKey={config.data.turnstileSiteKey} onToken={onToken} />
            ) : (
              <p className="text-sm text-destructive">Signup verification is not configured.</p>
            )
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <Button className="w-full" type="submit" disabled={pending || !signupReady}>
            {pending ? "Working…" : mode === "signup" ? "Create account" : "Sign in"}
          </Button>
        </form>
        <div className="mt-4 flex justify-between gap-3 text-sm">
          <a
            className="text-primary hover:underline"
            href={
              mode === "signup"
                ? `/login?returnTo=${encodeURIComponent(returnTo)}`
                : `/signup?returnTo=${encodeURIComponent(returnTo)}`
            }
          >
            {mode === "signup" ? "Already have an account?" : "Create an account"}
          </a>
          {mode === "login" ? (
            <a className="text-primary hover:underline" href="/forgot-password">
              Forgot password?
            </a>
          ) : null}
        </div>
        <Button asChild variant="ghost" className="mt-4 w-full">
          <a href={returnTo}>Continue without signing in</a>
        </Button>
      </section>
    </main>
  );
}
