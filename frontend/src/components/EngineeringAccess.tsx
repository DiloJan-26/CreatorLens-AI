"use client";
import {createContext,useCallback,useContext,useEffect,useRef,useState,type FormEvent,type ReactNode} from "react";
import {usePathname} from "next/navigation";
import {useAccount} from "./AccountProvider";
import {getEngineeringAccess,unlockEngineering,lockEngineering,type EngineeringAccess} from "@/lib/api";
import {Icon,PageHeading,Notice} from "./ui";

type State={access:EngineeringAccess|null;checking:boolean;busy:boolean;error:string|null;lockPending:boolean;
  unlock:(key:string)=>Promise<void>;lock:()=>Promise<void>;refresh:()=>Promise<void>};
const Context=createContext<State>({access:null,checking:true,busy:false,error:null,lockPending:false,unlock:async()=>{},lock:async()=>{},refresh:async()=>{}});
export function useEngineering(){return useContext(Context);}
const LOCK_EVENT="creatorlens_engineering_lock";

export function EngineeringProvider({children}:{children:ReactNode}) {
  const {account}=useAccount();const userId=account?.id;const pathname=usePathname();
  const [access,setAccess]=useState<EngineeringAccess|null>(null),[checking,setChecking]=useState(true),[busy,setBusy]=useState(false);
  const [error,setError]=useState<string|null>(null),[expiresAt,setExpiresAt]=useState<number|null>(null),[lockPending,setLockPending]=useState(false);
  const revision=useRef(0),pending=useRef(false),channel=useRef<BroadcastChannel|null>(null);
  const clear=useCallback(()=>{revision.current++;setAccess(null);setExpiresAt(null);setChecking(false);},[]);
  const apply=useCallback((value:EngineeringAccess)=>{
    if(!value || typeof value.configured!=="boolean" || typeof value.unlocked!=="boolean" ||
      !Number.isFinite(value.expires_in) || !Number.isFinite(value.duration_seconds) || value.duration_seconds<60 || value.duration_seconds>3600 ||
      value.expires_in<0 || value.expires_in>value.duration_seconds || value.unlocked&&(!value.configured||value.expires_in===0))throw new Error("Engineering access could not be verified.");
    setAccess(value);setExpiresAt(value.unlocked?Date.now()+value.expires_in*1000:null);setChecking(false);
  },[]);
  const refresh=useCallback(async()=>{
    const version=++revision.current;
    if(!userId){setAccess(null);setExpiresAt(null);setChecking(false);return;}
    setChecking(true);
    try {const value=await getEngineeringAccess();if(version===revision.current){apply(value);setError(null);}}
    catch(e){if(version===revision.current){setAccess(null);setExpiresAt(null);setChecking(false);setError(e instanceof Error?e.message:"Engineering access is unavailable.");}}
  },[userId,apply]);
  const invalidate=useCallback(()=>{revision.current++;},[]);
  // One status read on session setup; no periodic Redis polling.
  useEffect(()=>{const timer=setTimeout(()=>void refresh(),0);return()=>{clearTimeout(timer);invalidate();};},[refresh,invalidate]);
  useEffect(()=>{
    if(!expiresAt)return;
    const timer=setTimeout(clear,Math.max(0,expiresAt-Date.now()));
    return()=>clearTimeout(timer);
  },[expiresAt,clear]);
  useEffect(()=>{
    const denied=()=>{clear();setError("Engineering is locked or temporarily unavailable. Unlock again to continue.");};
    const session=()=>{clear();setError(null);};
    const recheck=()=>{if(document.visibilityState==="visible" && (pathname==="/evaluations"||pathname==="/dashboard")&&!pending.current)void refresh();};
    const storage=(event:StorageEvent)=>{if(event.key===LOCK_EVENT && event.newValue){clear();setError(null);}};
    if(typeof BroadcastChannel!=="undefined") {
      const bus=new BroadcastChannel("creatorlens-engineering");channel.current=bus;
      bus.onmessage=event=>{if(event.data?.accountId!==account?.id)return;if(event.data.type==="lock"){clear();setError(null);}else if(event.data.type==="refresh")void refresh();};
    }
    window.addEventListener("creatorlens_engineering_denied",denied);window.addEventListener("creatorlens_session_expired",session);
    window.addEventListener("storage",storage);document.addEventListener("visibilitychange",recheck);
    return()=>{window.removeEventListener("creatorlens_engineering_denied",denied);window.removeEventListener("creatorlens_session_expired",session);window.removeEventListener("storage",storage);document.removeEventListener("visibilitychange",recheck);channel.current?.close();channel.current=null;};
  },[account?.id,pathname,clear,refresh]);
  async function unlock(key:string) {
    if(pending.current)return;pending.current=true;setBusy(true);setError(null);
    const version=++revision.current;
    try {const value=await unlockEngineering(key);if(version===revision.current){apply(value);setLockPending(false);channel.current?.postMessage({type:"refresh",accountId:account?.id});}}
    catch(e){if(version===revision.current){setAccess(null);setExpiresAt(null);setChecking(false);setError(e instanceof Error?e.message:"Could not unlock Engineering.");}}
    finally{pending.current=false;setBusy(false);}
  }
  async function lock() {
    if(pending.current)return;pending.current=true;setBusy(true);clear();setError(null);setLockPending(true);
    try {const value=await lockEngineering();apply(value);setLockPending(false);}
    catch(e){setError(e instanceof Error?e.message:"The server lock could not be confirmed. Try again.");}
    finally {
      pending.current=false;setBusy(false);channel.current?.postMessage({type:"lock",accountId:account?.id});
      try{localStorage.setItem(LOCK_EVENT,String(Date.now()));localStorage.removeItem(LOCK_EVENT);}catch{}
    }
  }
  return <Context.Provider value={{access,checking,busy,error,lockPending,unlock,lock,refresh}}>{children}</Context.Provider>;
}

export function EngineeringIndicator() {
  const {access,checking,lockPending}=useEngineering();const unlocked=Boolean(access?.unlocked&&!checking&&!lockPending);
  const label=checking?"Checking Engineering access":unlocked?"Engineering unlocked":"Engineering locked";
  return <span className={`engineering-access-indicator ${unlocked?"is-unlocked":"is-locked"}`} role="status" aria-label={label} title={label}><Icon name={unlocked?"unlock":"lock"} size={14}/><span className="sr-only">{label}</span></span>;
}

export function EngineeringLockButton() {
  const {lock,busy}=useEngineering();
  return <button type="button" className="button-secondary engineering-lock-button" disabled={busy} onClick={()=>void lock()}><Icon name="lock" size={16}/>{busy?"Locking...":"Lock Engineering"}</button>;
}

export function EngineeringGate({children,title,icon}:{children:ReactNode;title:string;icon:string}) {
  const {access,checking,busy,error,lockPending,unlock,lock,refresh}=useEngineering();
  const [key,setKey]=useState("");
  async function submit(event:FormEvent){event.preventDefault();const supplied=key;setKey("");await unlock(supplied);}
  if(access?.unlocked&&!checking&&!lockPending)return <>{children}</>;
  return <main className="page-container engineering-view"><PageHeading eyebrow="Engineering" title={title} icon={icon}/>
    <section className="ui-panel engineering-unlock-panel" aria-labelledby="engineering-unlock-title">
      <span className="engineering-gate-icon"><Icon name="lock" size={24}/></span>
      <h2 id="engineering-unlock-title">Unlock Engineering</h2><p>One access key opens both Engineering dashboards for {Math.round((access?.duration_seconds??1800)/60)} minutes.</p>
      {checking?<p role="status">Checking access...</p>:lockPending?busy?<p role="status">Locking Engineering...</p>:<><Notice tone="error">{error??"Confirm the Engineering lock before continuing."}</Notice><button type="button" className="button-secondary" disabled={busy} onClick={()=>void lock()}>Retry lock</button></>:<>
        <form onSubmit={submit}><label htmlFor="engineering-key">Engineering access key</label><input id="engineering-key" name="engineering-key" type="password" value={key} autoComplete="off" spellCheck={false} maxLength={256} disabled={busy||access?.configured===false} onChange={event=>setKey(event.target.value)}/>
          <button type="submit" className="button-primary" disabled={busy||!key||access?.configured===false}><Icon name="unlock" size={16}/>{busy?"Unlocking...":"Unlock Engineering"}</button></form>
        {access?.configured===false&&<Notice>Engineering access has not been configured.</Notice>}{error&&<Notice tone="error">{error}</Notice>}
        {error&&<button type="button" className="source-link" disabled={busy} onClick={()=>void refresh()}>Check access</button>}
      </>}
    </section>
  </main>;
}
