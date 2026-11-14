"use client";
import { createContext,useContext,useEffect,useState,useCallback,useRef,type ReactNode } from "react";
import { usePathname,useRouter } from "next/navigation";
import Link from "next/link";
import { authEnabled,browserAuth } from "@/lib/supabase/browser";
import { clearAccountWorkspace } from "@/lib/app-session";
import { getAccount,revokeApplicationSession,type Account } from "@/lib/api";
import { Dialog } from "./ui";

type AccountState={enabled:boolean;account:Account|null;loading:boolean;refresh:()=>Promise<void>;logout:()=>Promise<void>};
const Context=createContext<AccountState>({enabled:false,account:null,loading:false,refresh:async()=>{},logout:async()=>{}});
export function useAccount(){return useContext(Context);}
export function AccountProvider({children}:{children:ReactNode}){
  const enabled=authEnabled(),pathname=usePathname(),router=useRouter();
  const [account,setAccount]=useState<Account|null>(null),[loading,setLoading]=useState(enabled),[error,setError]=useState<string|null>(null),[exhausted,setExhausted]=useState(false);
  const revision=useRef(0);
  const refresh=useCallback(async()=>{
    if(!enabled)return;
    const version=++revision.current;
    try {
      const {data,error}=await browserAuth().auth.getClaims();
      if(error || !data?.claims){setAccount(null);return;}
      const id=String(data.claims.sub);
      if(sessionStorage.getItem("creatorlens_account")!==id){clearAccountWorkspace();sessionStorage.setItem("creatorlens_account",id);}
      const value=await getAccount();
      if(version!==revision.current || value.id!==id)return;
      setAccount(value);setError(null);
    }catch(e){if(version===revision.current){setAccount(null);setError(e instanceof Error?e.message:"Account unavailable.");}}
    finally{if(version===revision.current)setLoading(false);}
  },[enabled]);
  useEffect(()=>{
    if(!enabled)return;
    let cancelled=false;
    const timer=setTimeout(()=>void refresh(),0);
    const {data}=browserAuth().auth.onAuthStateChange((event:import("@supabase/supabase-js").AuthChangeEvent,session:import("@supabase/supabase-js").Session|null)=>{
      revision.current++;
      if(session?.user?.id && session.user.id!==sessionStorage.getItem("creatorlens_account")){clearAccountWorkspace();setAccount(null);setLoading(true);}
      if(event==="SIGNED_OUT"){clearAccountWorkspace();setAccount(null);setLoading(false);}
      else setTimeout(()=>{if(!cancelled)void refresh();},0);
    });
    const expired=()=>{revision.current++;clearAccountWorkspace();setAccount(null);setError("Your session expired. Sign in again.");};
    const quota=()=>setExhausted(true);
    window.addEventListener("creatorlens_session_expired",expired);window.addEventListener("creatorlens_quota_exhausted",quota);
    return ()=>{cancelled=true;clearTimeout(timer);data.subscription.unsubscribe();window.removeEventListener("creatorlens_session_expired",expired);window.removeEventListener("creatorlens_quota_exhausted",quota);};
  },[enabled,refresh]);
  async function logout(){
    if(!enabled)return;
    revision.current++;
    // Revoke this application's session first. If unavailable, still clear browser credentials;
    // backend revocation failure is shown rather than claiming immediate remote invalidation.
    let revoked=false;
    try{await revokeApplicationSession();revoked=true;}catch{setError("Server session revocation could not be confirmed.");}
    const {error}=await browserAuth().auth.signOut();
    clearAccountWorkspace();setAccount(null);
    if(error || !revoked){setError("Signed out locally; server revocation requires verification.");return;}
    router.replace("/");router.refresh();
  }
  const isPublic=pathname==="/" || pathname.startsWith("/auth/") || pathname==="/login";
  return <Context.Provider value={{enabled,account,loading,refresh,logout}}>
    {enabled && !isPublic && loading ? <main className="page-container" role="status">Restoring your session...</main> : enabled && !isPublic && !account ? <main className="page-container"><h1 className="text-2xl font-semibold">Sign in to your workspace</h1><p className="mt-3" role="alert">{error??"Continue with Google to access your own analyses."}</p><Link className="button-primary mt-5" href="/login">Continue with Google</Link></main> : <div key={account?.id??"public"}>{children}</div>}
    <FreeAnalysisLimitDialog open={exhausted} onClose={()=>setExhausted(false)}/>
  </Context.Provider>;
}
export function AccountMenu(){
  const {enabled,account,loading,logout}=useAccount();
  if(!enabled)return <span className="demo-label">Restricted demo</span>;
  if(loading)return <span role="status">Restoring session...</span>;
  if(!account)return <Link className="button-secondary" href="/login">Sign in</Link>;
  return <div className="account-menu"><Link href="/workspace">{account.display_name??"Your workspace"}</Link><span className="text-sm">Free plan: {account.usage.available} of {account.usage.granted} available</span><button className="button-secondary" onClick={()=>void logout()}>Sign out</button></div>;
}

export function FreeAnalysisLimitDialog({open,onClose}:{open:boolean;onClose:()=>void}){
  return <Dialog open={open} onClose={onClose} title="Free analysis limit reached"><p>You&apos;ve used your five free comparisons. Your existing analyses remain available. Subscription plans are coming soon.</p><button className="button-secondary mt-4" onClick={onClose}>View existing analyses</button></Dialog>;
}
