import { createBrowserClient } from "@supabase/ssr";
let client: ReturnType<typeof createBrowserClient> | undefined;
export function authEnabled() { return process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE === "authenticated"; }
export function browserAuth() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error("Google sign-in is not configured.");
  return client ??= createBrowserClient(url, key);
}
