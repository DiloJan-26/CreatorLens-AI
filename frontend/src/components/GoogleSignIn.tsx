"use client";
import { useRef,useState,type ReactNode } from "react";
import Link from "next/link";
import { startGoogleSignIn } from "@/lib/google-auth";

export function GoogleSignInButton({children="Continue with Google",className="button-primary",disabled=false}:{children?:ReactNode;className?:string;disabled?:boolean}){
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null);
  const pending=useRef(false);
  async function signIn(){
    if(pending.current)return;
    pending.current=true;setBusy(true);setError(null);
    try {await startGoogleSignIn();}
    catch(e){setError(e instanceof Error?e.message:"Sign-in unavailable.");pending.current=false;setBusy(false);}
  }
  return <span className="google-entry"><button type="button" className={className} disabled={disabled||busy} aria-busy={busy} onClick={()=>void signIn()}>{busy?"Opening Google...":children}</button>{error&&<span className="auth-inline-error" role="alert">{error}</span>}</span>;
}
export function GoogleSignIn(){
  return <section className="ui-panel p-6 mx-auto max-w-lg"><p className="eyebrow">CreatorLens AI</p><h1 className="text-3xl font-semibold mt-3">Your evidence. Your workspace.</h1><p className="muted mt-4">Sign in or create your account with Google. Your analyses stay in your private workspace.</p><GoogleSignInButton className="button-primary mt-6"/><Link className="mt-4 block" href="/">Back to CreatorLens</Link></section>;
}
