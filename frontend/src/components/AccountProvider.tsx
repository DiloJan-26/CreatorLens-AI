"use client";
import { createContext,useContext,useEffect,useState,useCallback,useRef,type ReactNode } from "react";
import { usePathname,useRouter } from "next/navigation";
import Link from "next/link";
import { browserAuth } from "@/lib/supabase/browser";
import { clearAccountWorkspace } from "@/lib/app-session";
import { getAccount,revokeApplicationSession,type Account } from "@/lib/api";
import { Dialog } from "./ui";
import Image from "next/image";
import { GoogleSignInButton } from "./GoogleSignIn";

type AccountState={account:Account|null;loading:boolean;refresh:()=>Promise<void>;logout:()=>Promise<void>};
const Context=createContext<AccountState>({account:null,loading:false,refresh:async()=>{},logout:async()=>{}});
export function useAccount(){return useContext(Context);}
export function AccountProvider({children}:{children:ReactNode}){
  const pathname=usePathname(),router=useRouter();
  const [account,setAccount]=useState<Account|null>(null),[loading,setLoading]=useState(true),[error,setError]=useState<string|null>(null),[exhausted,setExhausted]=useState(false);
  const revision=useRef(0);
  const refresh=useCallback(async()=>{
    const version=++revision.current;
    try {
      const {data,error}=await browserAuth().auth.getClaims();
      if(version!==revision.current)return;
      if(error || !data?.claims){clearAccountWorkspace();setAccount(null);return;}
      const id=String(data.claims.sub);
      if(sessionStorage.getItem("creatorlens_account")!==id){clearAccountWorkspace();sessionStorage.setItem("creatorlens_account",id);}
      const value=await getAccount();
      if(version!==revision.current || value.id!==id)return;
      setAccount(value);setError(null);
    }catch(e){if(version===revision.current){setAccount(null);setError(e instanceof Error?e.message:"Account unavailable.");}}
    finally{if(version===revision.current)setLoading(false);}
  },[]);
  useEffect(()=>{
    let cancelled=false;
    const timer=setTimeout(()=>void refresh(),0);
    let client:ReturnType<typeof browserAuth>;
    try{client=browserAuth();}catch{return ()=>clearTimeout(timer);}
    const {data}=client.auth.onAuthStateChange((event:import("@supabase/supabase-js").AuthChangeEvent,session:import("@supabase/supabase-js").Session|null)=>{
      revision.current++;
      if(session?.user?.id && session.user.id!==sessionStorage.getItem("creatorlens_account")){clearAccountWorkspace();setAccount(null);setLoading(true);}
      if(event==="SIGNED_OUT"){clearAccountWorkspace();setAccount(null);setLoading(false);}
      else setTimeout(()=>{if(!cancelled)void refresh();},0);
    });
    const expired=()=>{revision.current++;clearAccountWorkspace();setAccount(null);setError("Your session expired. Sign in again.");};
    const quota=()=>setExhausted(true);
    window.addEventListener("creatorlens_session_expired",expired);window.addEventListener("creatorlens_quota_exhausted",quota);
    return ()=>{cancelled=true;clearTimeout(timer);data.subscription.unsubscribe();window.removeEventListener("creatorlens_session_expired",expired);window.removeEventListener("creatorlens_quota_exhausted",quota);};
  },[refresh]);
  async function logout(){
    revision.current++;
    // Revoke this application's session first. If unavailable, still clear browser credentials;
    // backend revocation failure is shown rather than claiming immediate remote invalidation.
    let revoked=false;
    try{await revokeApplicationSession();revoked=true;}catch{setError("Server session revocation could not be confirmed.");}
    let signedOut=false;
    try{const {error}=await browserAuth().auth.signOut();signedOut=!error;}
    catch{signedOut=false;}
    finally{revision.current++;clearAccountWorkspace();setAccount(null);setLoading(false);setExhausted(false);}
    if(!signedOut || !revoked){setError("Workspace cleared; sign-out could not be fully confirmed. Please retry.");return;}
    router.replace("/");router.refresh();
  }
  const isPublic=pathname==="/" || pathname.startsWith("/auth/") || pathname==="/login";
  return <Context.Provider value={{account,loading,refresh,logout}}>
    {!isPublic && loading ? <main className="page-container" role="status">Restoring your session...</main> : !isPublic && !account ? <main className="page-container"><h1 className="text-2xl font-semibold">Sign in to your workspace</h1><p className="mt-3" role="alert">{error??"Continue with Google to access your own analyses."}</p><GoogleSignInButton className="button-primary mt-5"/></main> : <div key={account?.id??"public"}>{children}</div>}
    {isPublic&&error&&<p className="auth-status-notice" role="alert">{error}</p>}
    <FreeAnalysisLimitDialog open={exhausted} onClose={()=>setExhausted(false)}/>
  </Context.Provider>;
}
export function AccountMenu(){
  const {account,loading,logout}=useAccount();
  const [busy,setBusy]=useState(false),[photoFailed,setPhotoFailed]=useState(false);
  const menu=useRef<HTMLDetailsElement>(null),pending=useRef(false);
  useEffect(()=>{
    const close=(event:PointerEvent)=>{if(menu.current&&!menu.current.contains(event.target as Node))menu.current.open=false;};
    document.addEventListener("pointerdown",close);
    return ()=>document.removeEventListener("pointerdown",close);
  },[]);
  if(loading)return <span role="status" className="muted text-sm">Restoring session...</span>;
  if(!account)return <GoogleSignInButton className="button-secondary">Sign in</GoogleSignInButton>;
  const name=account.display_name?.trim()||account.email?.split("@")[0]||"Your account";
  const initials=name.split(/\s+/).slice(0,2).map(word=>Array.from(word)[0]).join("").toUpperCase();
  let photo:string|undefined;
  try {const url=new URL(account.avatar_url??"");if(url.protocol==="https:"&&(url.hostname==="googleusercontent.com"||url.hostname.endsWith(".googleusercontent.com")))photo=url.href;}catch{}
  async function signOut(){
    if(pending.current)return;
    pending.current=true;setBusy(true);
    try{await logout();}finally{pending.current=false;setBusy(false);}
  }
  return <details className="profile-menu" ref={menu} onKeyDown={event=>{if(event.key==="Escape"){event.preventDefault();if(menu.current){menu.current.open=false;menu.current.querySelector("summary")?.focus();}}}} onBlur={event=>{if(!event.currentTarget.contains(event.relatedTarget as Node)&&menu.current)menu.current.open=false;}}>
    <summary className="profile-trigger" aria-label={`Account for ${name}`}><span className="profile-avatar">{photo&&!photoFailed?<Image src={photo} alt="" width={36} height={36} unoptimized referrerPolicy="no-referrer" onError={()=>setPhotoFailed(true)}/>:initials}</span><span className="profile-trigger-name">{name}</span><svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="m6 9 6 6 6-6"/></svg></summary>
    <div className="profile-dropdown">
      <div className="profile-identity"><strong>{name}</strong>{account.email&&<span>{account.email}</span>}</div>
      <Link href="/workspace" className="profile-workspace" onClick={()=>{if(menu.current)menu.current.open=false;}}>Workspace</Link>
      <p className="profile-allowance">{account.usage.available} of {account.usage.granted} analyses available</p>
      <button type="button" className="profile-signout" disabled={busy} onClick={()=>void signOut()}>{busy?"Signing out...":"Sign out"}</button>
    </div>
  </details>;
}

export function FreeAnalysisLimitDialog({open,onClose}:{open:boolean;onClose:()=>void}){
  return <Dialog open={open} onClose={onClose} title="Free analysis limit reached"><p>You&apos;ve used your available free comparisons. Your existing analyses remain available. Subscription plans are coming soon.</p><button className="button-secondary mt-4" onClick={onClose}>View existing analyses</button></Dialog>;
}
