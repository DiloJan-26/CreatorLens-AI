"use client";
import { useState } from "react";
import Link from "next/link";
import { browserAuth,authEnabled } from "@/lib/supabase/browser";
export function GoogleSignIn(){
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  async function signIn(){
    if(!authEnabled()){setError("Authenticated access has not been enabled for this installation.");return;}
    setBusy(true);setError(null);
    try {
      const origin=process.env.NEXT_PUBLIC_SITE_URL??(process.env.NODE_ENV==="development"?"http://localhost:3000":"");
      if(!origin || new URL(origin).origin!==window.location.origin)throw new Error("The trusted sign-in origin is not configured for this site.");
      const {error}=await browserAuth().auth.signInWithOAuth({provider:"google",options:{redirectTo:origin+"/auth/callback",scopes:"openid email profile"}});
      if(error)throw new Error("Google sign-in could not be started. Please try again.");
    }catch(e){setError(e instanceof Error?e.message:"Sign-in unavailable.");setBusy(false);}
  }
  return <section className="ui-panel p-6 mx-auto max-w-lg"><p className="eyebrow">CreatorLens AI</p><h1 className="text-3xl font-semibold mt-3">Your evidence. Your workspace.</h1><p className="muted mt-4">Continue with Google to manage your analyses. The free plan includes five lifetime two-video comparisons.</p><button className="button-primary mt-6" disabled={busy} onClick={()=>void signIn()}>{busy?"Opening Google...":"Continue with Google"}</button>{error&&<p className="mt-4" role="alert">{error}</p>}<p className="muted text-sm mt-5">Email/password sign-in and payments are not offered.</p><Link className="mt-4 inline-block" href="/">Back to CreatorLens</Link></section>;
}
