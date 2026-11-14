/* Isolated SDK, transport and SSR contract checks. No browser or external connections. */
import fs from "node:fs";
import path from "node:path";
import Module from "node:module";
import assert from "node:assert/strict";
import ts from "typescript";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
const root=path.resolve("src");
let enabled=true,token="synthetic-access-token",callbackError=null,proxyClaims=null;
const cookieJar=()=>{const rows=[];return {set(...args){rows.push(args.length===1?args[0]:{name:args[0],value:args[1],...args[2]});},getAll:()=>rows};};
const calls=[],events=[];
const storage=()=>{const data=new Map();return {get length(){return data.size;},key:i=>[...data.keys()][i],getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};};
globalThis.window={localStorage:storage(),sessionStorage:storage(),dispatchEvent:event=>events.push(event.type),location:{origin:"http://localhost:3000"}};
globalThis.CustomEvent=class extends Event{constructor(type,init){super(type);this.detail=init?.detail;}};
const sdk={auth:{getSession:async()=>({data:{session:token?{access_token:token}:null},error:null})}};
const cache=new Map();
function load(file){
  file=path.resolve(file);
  if(cache.has(file))return cache.get(file).exports;
  const compiledModule=new Module(file);cache.set(file,compiledModule);compiledModule.filename=file;compiledModule.paths=Module._nodeModulePaths(path.dirname(file));
  compiledModule.require=name=>{
    if(name.endsWith("supabase/browser"))return {authEnabled:()=>enabled,browserAuth:()=>sdk};
    if(name==="@/lib/supabase/server")return {siteOrigin:()=>"http://localhost:3000",serverAuth:async()=>({auth:{exchangeCodeForSession:async code=>{calls.push({code});return {error:callbackError};}}})};
    if(name==="@supabase/ssr")return {createServerClient:(url,key,options)=>({auth:{getClaims:async()=>{options.cookies.setAll([{name:"sb-fixture",value:"synthetic-cookie",options:{path:"/"}}]);return {data:proxyClaims?{claims:proxyClaims}:null,error:null};}}})};
    if(name==="next/server")return {NextResponse:class {constructor(body,init){this.body=body;this.status=init?.status;}static next(){return {headers:new Headers(),cookies:cookieJar()};}static redirect(location,init){return {location:String(location),headers:init?.headers??new Headers(),cookies:cookieJar()};}}};
    if(name==="next/navigation")return {usePathname:()=>"/login"};
    if(name==="next/link")return function MockLink({children,...props}){return React.createElement("a",props,children);};
    if(name==="./ui")return {Dialog:function MockDialog({children,title,open}){return open?React.createElement("section",null,React.createElement("h2",null,title),children):null;}};
    if(name.startsWith("@/")||name.startsWith("./")){
      const base=name.startsWith("@/")?path.join(root,name.slice(2)):path.resolve(path.dirname(file),name);
      const target=[base,base+".ts",base+".tsx"].find(file=>fs.existsSync(file)&&fs.statSync(file).isFile());
      if(target)return load(target);
    }
    return Module.prototype.require.call(compiledModule,name);
  };
  const code=ts.transpileModule(fs.readFileSync(file,"utf8"),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
  compiledModule._compile(code,file);return compiledModule.exports;
}
const transport=load(path.join(root,"lib/auth-transport.ts"));
assert.equal((await transport.authorizedHeaders({"Content-Type":"application/json"})).get("Authorization"),"Bearer synthetic-access-token");
assert.equal((await transport.authorizedHeaders({"Content-Type":"application/json"})).get("Content-Type"),"application/json");
token=null;await assert.rejects(()=>transport.authorizedHeaders(),error=>error.status===401);token="synthetic-access-token";
enabled=false;assert.equal((await transport.authorizedHeaders()).get("Authorization"),null);enabled=true;
const session=load(path.join(root,"lib/app-session.ts"));
session.setActiveProjectId("owned-project");session.setChatSessionId("owned-project","owned-session");session.setChatDraft("owned-project","private draft");session.setComparisonObjective("owned-project","engagement");
window.localStorage.setItem("unrelated","preserved");session.clearAccountWorkspace();
assert.equal(session.getActiveProjectId(),null);assert.equal(session.getChatSessionId("owned-project"),null);assert.equal(session.getChatDraft("owned-project"),"");assert.equal(session.getComparisonObjective("owned-project"),"balanced");assert.equal(window.localStorage.getItem("unrelated"),"preserved");
const api=load(path.join(root,"lib/api.ts"));
globalThis.fetch=async(url,init)=>{calls.push({url:String(url),init});return new Response(JSON.stringify({id:"owned-user"}),{status:200});};
await api.getAccount();assert.equal(calls.at(-1).init.headers.get("Authorization"),"Bearer synthetic-access-token");assert(!calls.at(-1).url.includes("synthetic-access-token"));assert.equal(calls.at(-1).init.redirect,"error");
globalThis.fetch=async(url,init)=>{calls.push({url:String(url),init});return new Response('event: done\ndata: {"status":"complete"}\n\n',{headers:{"Content-Type":"text/event-stream"}});};
await api.streamChatResponse("owned-project",{session_id:"owned-session",message:"views"},{});assert.equal(calls.at(-1).init.headers.get("Authorization"),"Bearer synthetic-access-token");assert(!calls.at(-1).url.includes("synthetic-access-token"));
globalThis.fetch=async()=>new Response(JSON.stringify({detail:"Session expired"}),{status:401});await assert.rejects(()=>api.getAccount(),error=>error.status===401);assert(events.includes("creatorlens_session_expired"));
globalThis.fetch=async()=>new Response(JSON.stringify({detail:{code:"analysis_limit_reached",message:"Free analysis limit reached"}}),{status:403});await assert.rejects(()=>api.getAccount(),error=>error.message==="Free analysis limit reached");assert(events.includes("creatorlens_quota_exhausted"));
globalThis.fetch=async()=>new Response(JSON.stringify({detail:"Try later"}),{status:429,headers:{"Retry-After":"42"}});await assert.rejects(()=>api.getAccount(),error=>error.status===429&&error.retryAfter==="42");
const {GoogleSignIn}=load(path.join(root,"components/GoogleSignIn.tsx"));const login=renderToStaticMarkup(React.createElement(GoogleSignIn));assert(login.includes("Continue with Google")&&!login.includes('type="password"'));
const {FreeAnalysisLimitDialog}=load(path.join(root,"components/AccountProvider.tsx"));const dialog=renderToStaticMarkup(React.createElement(FreeAnalysisLimitDialog,{open:true,onClose:()=>{}}));assert(dialog.includes("Free analysis limit reached")&&dialog.includes("Your existing analyses remain available.")&&dialog.includes("Subscription plans are coming soon.")&&!dialog.includes("checkout"));
const callback=load(path.join(root,"app/auth/callback/route.ts"));let response=await callback.GET({nextUrl:new URL("http://localhost:3000/auth/callback?code=fixture-code&next=https://attacker.invalid")});assert.equal(response.location,"http://localhost:3000/workspace");assert.equal(response.headers["Cache-Control"],"private, no-store");
callbackError=new Error("synthetic failure");response=await callback.GET({nextUrl:new URL("http://localhost:3000/auth/callback?code=invalid")});assert.equal(response.location,"http://localhost:3000/login?error=oauth");
console.log("Auth contracts passed: Bearer transport, authenticated SSE, session/cache clearing, 401/403/429, Google-only UI, quota dialog and fixed PKCE callback destination. SDK mocked; not live OAuth/browser acceptance.");

process.env.APPLICATION_ACCESS_MODE="authenticated";process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE="authenticated";
process.env.NEXT_PUBLIC_SUPABASE_URL="https://auth.example";process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="synthetic-publishable-key";process.env.NEXT_PUBLIC_SITE_URL="https://creatorlens.example";
const {proxy}=load(path.join(root,"proxy.ts"));
const request={nextUrl:new URL("https://untrusted.invalid/analyze?next=https://attacker.invalid"),cookies:{getAll:()=>[],set:()=>{}}};
response=await proxy(request);assert.equal(response.location,"https://creatorlens.example/login");assert.equal(response.headers.get("Cache-Control"),"private, no-store");assert.equal(response.cookies.getAll()[0].name,"sb-fixture");
proxyClaims={sub:"synthetic-user"};response=await proxy(request);assert.equal(response.location,undefined);assert.equal(response.headers.get("Cache-Control"),"private, no-store");
process.env.NEXT_PUBLIC_SITE_URL="";response=await proxy(request);assert.equal(response.status,503);
console.log("Proxy contracts passed: verified-claim gating, refresh-cookie propagation, trusted-origin redirect and missing-configuration denial. SDK mocked.");
