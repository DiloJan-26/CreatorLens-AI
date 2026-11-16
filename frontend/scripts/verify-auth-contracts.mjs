/* Isolated SDK, transport and SSR contract checks. No browser or external connections. */
import fs from "node:fs";
import path from "node:path";
import Module from "node:module";
import assert from "node:assert/strict";
import ts from "typescript";
import React from "react";
import {renderToStaticMarkup} from "react-dom/server";
const root=path.resolve("src");
let proxyThrows=false,token="synthetic-access-token",callbackError=null,callbackThrows=false,proxyClaims=null;
const cookieJar=()=>{const rows=[];return {set(...args){rows.push(args.length===1?args[0]:{name:args[0],value:args[1],...args[2]});},getAll:()=>rows};};
const calls=[],events=[];
const storage=()=>{const data=new Map();return {get length(){return data.size;},key:i=>[...data.keys()][i],getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};};
globalThis.window={localStorage:storage(),sessionStorage:storage(),dispatchEvent:event=>events.push(event.type),location:{origin:"http://localhost:3000"}};
globalThis.CustomEvent=class extends Event{constructor(type,init){super(type);this.detail=init?.detail;}};
let oauthError=null;const oauthCalls=[];
const sdk={auth:{signInWithOAuth:async options=>{oauthCalls.push(options);return {error:oauthError};},getSession:async()=>({data:{session:token?{access_token:token}:null},error:null})}};
const cache=new Map();
function load(file){
  file=path.resolve(file);
  if(cache.has(file))return cache.get(file).exports;
  const compiledModule=new Module(file);cache.set(file,compiledModule);compiledModule.filename=file;compiledModule.paths=Module._nodeModulePaths(path.dirname(file));
  compiledModule.require=name=>{
    if(name.endsWith("supabase/browser"))return {browserAuth:()=>sdk};
    if(name==="@/lib/supabase/server")return {siteOrigin:()=>"http://localhost:3000",serverAuth:async()=>({auth:{exchangeCodeForSession:async code=>{calls.push({code});if(callbackThrows)throw Error("Synthetic SDK failure");return {error:callbackError};}}})};
    if(name==="@supabase/ssr")return {createServerClient:(url,key,options)=>({auth:{getClaims:async()=>{if(proxyThrows)throw Error("Synthetic verification outage");options.cookies.setAll([{name:"sb-fixture",value:"synthetic-cookie",options:{path:"/"}}]);return {data:proxyClaims?{claims:proxyClaims}:null,error:null};}}})};
    if(name==="next/server")return {NextResponse:class {constructor(body,init){this.body=body;this.status=init?.status;}static next(){return {headers:new Headers(),cookies:cookieJar()};}static redirect(location,init){return {location:String(location),headers:init?.headers??new Headers(),cookies:cookieJar()};}}};
    if(name==="next/navigation")return {usePathname:()=>"/login"};
    if(name==="next/image")return function MockImage(props){const imageProps={...props};delete imageProps.unoptimized;delete imageProps.priority;return React.createElement("img",imageProps);};
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
process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE="disabled";assert.equal((await transport.authorizedHeaders()).get("Authorization"),"Bearer synthetic-access-token");
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

process.env.APPLICATION_ACCESS_MODE="disabled";process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE="disabled";
process.env.NEXT_PUBLIC_SUPABASE_URL="https://auth.example";process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="synthetic-publishable-key";process.env.NEXT_PUBLIC_SITE_URL="https://creatorlens.example";
const {proxy}=load(path.join(root,"proxy.ts"));
const request={nextUrl:new URL("https://untrusted.invalid/analyze?next=https://attacker.invalid"),cookies:{getAll:()=>[],set:()=>{}}};
response=await proxy(request);assert.equal(response.location,"https://creatorlens.example/login");assert.equal(response.headers.get("Cache-Control"),"private, no-store");assert.equal(response.cookies.getAll()[0].name,"sb-fixture");
proxyClaims={sub:"synthetic-user"};response=await proxy(request);assert.equal(response.location,undefined);assert.equal(response.headers.get("Cache-Control"),"private, no-store");
process.env.NEXT_PUBLIC_SITE_URL="";response=await proxy(request);assert.equal(response.status,503);
proxyThrows=true;response=await proxy(request);assert.equal(response.status,503);proxyThrows=false;
console.log("Proxy contracts passed: verified-claim gating, refresh-cookie propagation, trusted-origin redirect and missing-configuration denial. SDK mocked.");

callbackThrows=true;response=await callback.GET({nextUrl:new URL("http://localhost:3000/auth/callback?code=private-fixture-code")});assert.equal(response.location,"http://localhost:3000/login?error=oauth");callbackThrows=false;
process.env.NEXT_PUBLIC_SITE_URL="https://creatorlens.example";
process.env.APPLICATION_ACCESS_MODE="disabled";process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE="authenticated";response=await proxy(request);assert.equal(response.headers.get("Cache-Control"),"private, no-store");
process.env.APPLICATION_ACCESS_MODE="authenticated";process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE="disabled";response=await proxy(request);assert.equal(response.headers.get("Cache-Control"),"private, no-store");
console.log("Acceptance regressions passed: callback failures fail closed; obsolete mode variables cannot disable authentication.");

const nextConfigSource=fs.readFileSync(path.resolve("next.config.ts"),"utf8");
const nextConfigCode=ts.transpileModule(nextConfigSource,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const configModule=new Module(path.resolve("next.config.ts"));configModule._compile(nextConfigCode,"next.config.ts");
const ignored=configModule.exports.default.logging.incomingRequests.ignore;
assert(ignored.some(pattern=>pattern.test("/auth/callback?code=synthetic-sensitive-code")));
assert(!ignored.some(pattern=>pattern.test("/workspace")));
console.log("OAuth callback development request logs suppressed without hiding normal workspace requests.");

// Public build-time configuration never becomes an authorization or quota authority.
{
  const keys=["NODE_ENV","NEXT_PUBLIC_API_BASE_URL","NEXT_PUBLIC_APPLICATION_ACCESS_MODE","NEXT_PUBLIC_STATUS_POLL_INTERVAL_MS"];
  const previous=Object.fromEntries(keys.map(key=>[key,process.env[key]]));
  const apiFile=path.join(root,"lib/api.ts"),uiFile=path.join(root,"lib/ui-config.ts");
  try {
    process.env.NODE_ENV="production";
    process.env.NEXT_PUBLIC_APPLICATION_ACCESS_MODE="authenticated";
    process.env.NEXT_PUBLIC_API_BASE_URL="http://insecure.invalid";
    cache.delete(apiFile);assert.throws(()=>load(apiFile),/trusted API origin/);
    process.env.NEXT_PUBLIC_API_BASE_URL="https://api.fixture.invalid";
    cache.delete(apiFile);assert.equal(typeof load(apiFile).checkBackend,"function");
    process.env.NEXT_PUBLIC_STATUS_POLL_INTERVAL_MS="1500";
    cache.delete(uiFile);assert.equal(load(uiFile).uiConfig.pollIntervalMs,1500);
    process.env.NEXT_PUBLIC_STATUS_POLL_INTERVAL_MS="0";
    cache.delete(uiFile);assert.throws(()=>load(uiFile),/Invalid public polling/);
    for (const component of ["GoogleSignIn.tsx","AccountProvider.tsx"]) {
      assert(!fs.readFileSync(path.join(root,"components",component),"utf8").includes("five free comparisons"));
    }
  } finally {
    for (const key of keys) { if(previous[key]===undefined)delete process.env[key];else process.env[key]=previous[key]; }
    cache.delete(apiFile);cache.delete(uiFile);
  }
  console.log("Configuration contracts passed: trusted deployed API origins, bounded environment-driven polling and no fixed client credit promise.");
}

// The same Google OAuth redirect serves registration and return sign-in.
process.env.NEXT_PUBLIC_SITE_URL="https://wrong.fixture.invalid";
const {startGoogleSignIn}=load(path.join(root,"lib/google-auth.ts"));
await assert.rejects(()=>startGoogleSignIn(),/trusted sign-in origin/);
assert.equal(oauthCalls.length,0);
process.env.NEXT_PUBLIC_SITE_URL=window.location.origin;
oauthError=Error("private SDK details");
await assert.rejects(()=>startGoogleSignIn(),error=>error.message==="Google sign-in could not be started. Please try again.");
oauthError=null;oauthCalls.length=0;
await Promise.all([startGoogleSignIn(),startGoogleSignIn()]);
assert.equal(oauthCalls.length,1);
assert.equal(oauthCalls[0].provider,"google");
assert.equal(oauthCalls[0].options.redirectTo,window.location.origin+"/auth/callback");
assert.equal(oauthCalls[0].options.queryParams.prompt,"select_account");
assert.equal(oauthCalls[0].options.scopes,"openid email profile");
const navbar=fs.readFileSync(path.join(root,"components/AppNavbar.tsx"),"utf8");
assert(!navbar.includes("setAuth")&&!navbar.includes("open={auth}"));
for(const file of ["app/page.tsx","components/WorkspaceCTA.tsx","components/LandingHero.tsx","components/LandingComparisonPreview.tsx"]){
  const source=fs.readFileSync(path.join(root,file),"utf8");assert(source.includes("WorkspaceEntry"));assert(!/href="\/analyze"/.test(source));
}
console.log("Direct OAuth contracts passed: trusted callback, Google-only identity, account chooser, duplicate suppression, recoverable errors and shared public entry actions without sign-in dialogs.");
