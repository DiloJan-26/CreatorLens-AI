/* Real Chromium interactions over actual components; SDK/API fixtures only.
   No Next.js server, real OAuth, provider, database or cloud access. */
import fs from 'node:fs';import path from 'node:path';import os from 'node:os';import http from 'node:http';import assert from 'node:assert/strict';import {createRequire} from 'node:module';import {fileURLToPath} from 'node:url';
const nodeRequire=createRequire(import.meta.url),__dirname=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(__dirname,'..'), repo=path.dirname(root);
const fixtureDir=fs.mkdtempSync(path.join(os.tmpdir(),'creatorlens-browser-'));
const out=path.join(repo,'docs/CreatorLens-Intelligence-v2/verification');fs.mkdirSync(out,{recursive:true});
const packagePath=process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE;
if(!packagePath)throw Error('Set ACCEPTANCE_PLAYWRIGHT_PACKAGE to an existing installed Playwright package; no downloads are performed.');
const {chromium}=nodeRequire(packagePath);
const webpack=nodeRequire('next/dist/compiled/webpack/webpack').webpack;
function write(name,value){const p=path.join(fixtureDir,name);fs.writeFileSync(p,value);return p;}
const reactPath=JSON.stringify(nodeRequire.resolve('react'));
const nav=write('navigation.cjs',`exports.usePathname=()=>location.pathname;exports.useSearchParams=()=>new URLSearchParams(location.search);exports.useRouter=()=>({replace:p=>location.assign(p),push:p=>location.assign(p),refresh:()=>{}});`);
const link=write('link.cjs',`const React=require(${reactPath});module.exports=function Link({children,prefetch,replace,scroll,...props}){return React.createElement('a',props,children)};`);
const image=write('image.cjs',`const React=require(${reactPath});module.exports=function Image({priority,fill,unoptimized,quality,...props}){return React.createElement('img',props)};`);
const auth=write('auth.cjs',`exports.authEnabled=()=>true;exports.browserAuth=()=>window.__fixture.sdk;`);
const api=write('api.cjs',`module.exports=new Proxy({}, {get:(_,name)=> name==='__esModule'?false:(...args)=>window.__fixture.api(name,...args)});`);
const loader=write('loader.cjs',`const ts=require(${JSON.stringify(nodeRequire.resolve('typescript'))});module.exports=function(source){return ts.transpileModule(source,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText};`);
const entry=write('entry.tsx',`
import React,{useState} from 'react';import {createRoot} from 'react-dom/client';
import {AccountProvider} from '${root.replaceAll('\\','/')}/src/components/AccountProvider';
import {AppNavbar} from '${root.replaceAll('\\','/')}/src/components/AppNavbar';
import {AccountWorkspace} from '${root.replaceAll('\\','/')}/src/components/AccountWorkspace';
import {GoogleSignIn} from '${root.replaceAll('\\','/')}/src/components/GoogleSignIn';
import {ComparisonWorkspace} from '${root.replaceAll('\\','/')}/src/components/ComparisonWorkspace';
import {GoalComparisonPanel} from '${root.replaceAll('\\','/')}/src/components/GoalComparisonPanel';
import {ExecutiveInsightSnapshot} from '${root.replaceAll('\\','/')}/src/components/ExecutiveInsightSnapshot';
import {CreatorRecommendationList} from '${root.replaceAll('\\','/')}/src/components/CreatorRecommendationList';
import {SemanticAnalysisPanel} from '${root.replaceAll('\\','/')}/src/components/SemanticAnalysisPanel';
import {CreatorChatPanel} from '${root.replaceAll('\\','/')}/src/components/CreatorChatPanel';
import Landing from '${root.replaceAll('\\','/')}/src/app/page';
import Evaluation from '${root.replaceAll('\\','/')}/src/app/evaluations/page';
import Dashboard from '${root.replaceAll('\\','/')}/src/app/dashboard/page';
const listeners=new Set();let user='A',available=5,reserved=0;const calls=[];
function account(){return {id:'fixture-'+user,display_name:'Acceptance '+user,email:null,role:'user',plan:'free',usage:{granted:5,available,reserved,completed:5-available-reserved}}}
function summary(objective='balanced'){return {project_id:'synthetic-browser',goal_comparison:{selected_objective:objective,outcome:objective==='reach'?'content_2':objective==='engagement'?'content_1':'insufficient_evidence',winner_slot:objective==='reach'?'content_2':objective==='engagement'?'content_1':null,eligibility:{status:objective==='reach'||objective==='engagement'?'eligible':'insufficient_evidence'},raw_objective_values:{content_1:objective==='reach'?34021:objective==='engagement'?1.449104:null,content_2:objective==='reach'?1527222:objective==='engagement'?1.256137:null},objective_units:objective==='reach'?'views':objective==='engagement'?'percent':'score /10',explanation:objective==='reach'?'Content 2 leads in observed public views. Synthetic fixture.':objective==='engagement'?'Content 1 has the higher descriptive engagement rate. Synthetic fixture.':'Compatible semantic evidence is unavailable. Synthetic fixture.',missing_evidence:objective==='balanced'||objective==='creative_quality'?['Current compatible semantic features']:[],dimension_leaders:{},limitations:['Offline synthetic fixture; no live provider or semantic assessment.'],decision_policy_version:'goal-comparison-1.0.0',metric_policy_version:'creator-insight-2.0.0',creative_policy_version:null}}}
const sdk={auth:{getClaims:async()=>{const result={data:{claims:user?{sub:'fixture-'+user}:null},error:null};if(window.__fixture.deferClaims)return new Promise(resolve=>window.__fixture.pendingClaims.push(()=>resolve(result)));return result},getSession:async()=>({data:{session:user?{access_token:'synthetic-fixture-only'}:null},error:null}),onAuthStateChange:cb=>{listeners.add(cb);return {data:{subscription:{unsubscribe:()=>listeners.delete(cb)}}}},signOut:async()=>{if(window.__fixture.rejectLogout)throw Error('Synthetic SDK failure');user=null;for(const cb of listeners)cb('SIGNED_OUT',null);return {error:null}},signInWithOAuth:async()=>({error:Error('Offline OAuth is intentionally not sent')})}};
window.__fixture={sdk,calls,account,deferClaims:false,pendingClaims:[],switchUser(next){user=next;available=5;reserved=0;for(const cb of listeners)cb('SIGNED_IN',{user:{id:'fixture-'+next}})},setBalance(n,r=0){available=n;reserved=r},rejectLogout:false,summary,async api(name,...args){calls.push(name);switch(name){case 'getAccount':return account();case 'getAccountUsage':return {balance:account().usage,events:[],analyses:[]};case 'listOwnedProjects':return {projects:[]};case 'revokeApplicationSession':return {status:'signed_out'};case 'getCreatorInsightSummary':return summary(args[1]);case 'getEvaluationDatasets':return [];case 'getEvaluationRuns':case 'getCostMetrics':throw Error('Administrator or owned project required (synthetic 403)');case 'getDemoCapabilities':return {mode:'authenticated',provider_calls_enabled:false,semantic_generation_enabled:false,reason:'Provider generation is disabled'};case 'getSemanticAnalysis':return {project_id:args[0],slot:args[1],status:'unavailable',error_code:'EVIDENCE_UNAVAILABLE',error_message:'Synthetic evidence unavailable'};case 'createProject':return {project_id:'synthetic-browser'};case 'startProjectIngestion':throw Error('Paid provider operations are disabled (synthetic 403)');case 'getChatHistory':return {messages:[],session_id:'synthetic-session'};default:throw Error('Unconfigured offline fixture: '+name)}}};
function Comparison(){const [value,setValue]=useState(summary());return <main className="page-container"><ExecutiveInsightSnapshot summary={value}/><GoalComparisonPanel summary={value} onChange={setValue}/><CreatorRecommendationList contents={[]} bundle={{project_id:'synthetic-browser',policy_version:'creator-recommendations-1.0.0',selected_objective:value.goal_comparison.selected_objective,recommendations:[],findings:[],limitations:['No validated semantic features in this synthetic fixture.']}}/><SemanticAnalysisPanel projectId="synthetic-browser" slot="content_1" onReady={()=>{}}/></main>}
const route=location.pathname;
const body=route==='/'?<Landing/>:route==='/login'?<main className="page-container">{location.search&&<p role="alert">OAuth callback failed (synthetic state).</p>}<GoogleSignIn/></main>:route==='/workspace'?<AccountWorkspace/>:route==='/analyze'?<ComparisonWorkspace/>:route==='/comparison'?<Comparison/>:route==='/chat'?<main className="page-container"><CreatorChatPanel projectId={null} indexReady={false}/></main>:route==='/evaluations'?<Evaluation/>:route==='/dashboard'?<Dashboard/>:<p>Unknown fixture route.</p>;
createRoot(document.getElementById('root')!).render(<><p style={{padding:8,background:'#fff2bd',fontSize:13}}>OFFLINE COMPONENT ACCEPTANCE ? synthetic identity, SDK and API; no live OAuth/provider.</p><AccountProvider><AppNavbar>{body}</AppNavbar></AccountProvider></>);
`);
async function main(){
 const cssFiles=[];function find(dir){if(!fs.existsSync(dir))return;for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())find(p);else if(p.endsWith('.css'))cssFiles.push(p)}}find(path.join(root,'.next/static'));
 assert(cssFiles.length,'Run the existing frontend build first; compiled CSS is required.');
 const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://localhost');if(url.pathname==='/bundle.js'){res.setHeader('Content-Type','text/javascript');return fs.createReadStream(path.join(fixtureDir,'bundle.js')).pipe(res)}if(url.pathname==='/styles.css'){res.setHeader('Content-Type','text/css');return res.end(cssFiles.map(p=>fs.readFileSync(p,'utf8')).join('\n'))}if(url.pathname.startsWith('/Logo/')){const p=path.join(root,'public',url.pathname);if(fs.existsSync(p))return fs.createReadStream(p).pipe(res)}res.setHeader('Content-Type','text/html');res.end('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/styles.css"></head><body><div id="root"></div><script src="/bundle.js"></script></body></html>')});
 await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin='http://127.0.0.1:'+server.address().port;
 await new Promise((resolve,reject)=>webpack({mode:'development',devtool:false,target:'web',entry,output:{path:fixtureDir,filename:'bundle.js'},resolve:{extensions:['.tsx','.ts','.js','.cjs','.mjs','.json'],modules:[path.join(root,'node_modules'),'node_modules'],alias:{'@/lib/supabase/browser':auth,'@/lib/api':api,'@':path.join(root,'src'),'next/navigation':nav,'next/link':link,'next/image':image}},module:{rules:[{test:/\.tsx?$/,exclude:/node_modules/,use:loader}]},plugins:[new webpack.DefinePlugin({'process.env.NEXT_PUBLIC_SITE_URL':JSON.stringify(origin)})]},(error,stats)=>{if(error||stats.hasErrors())reject(error||Error(stats.toString({all:false,errors:true})));else resolve()}));
 const browser=await chromium.launch({headless:true,args:['--disable-background-networking']});const results=[],errors=[];
 try{
 for(const width of [1440,1024,768,390]){console.log('Testing viewport',width);
  const context=await browser.newContext({viewport:{width,height:900}});
  await context.route('**/*',route=>new URL(route.request().url()).origin===origin?route.continue():route.abort());
  const page=await context.newPage();page.setDefaultTimeout(8000);page.setDefaultNavigationTimeout(15000);page.on('pageerror',e=>errors.push({width,message:e.message}));
  for(const route of ['/','/login','/login?error=oauth','/workspace','/analyze','/comparison','/chat','/evaluations','/dashboard']){
   console.log('Route',width,route);await page.goto(origin+route);await page.waitForFunction(()=>document.querySelector('main, .landing, .page-container'));
   await page.waitForFunction(()=>!document.body.textContent.includes('Restoring your session...'));
   await page.screenshot({path:path.join(out,`browser-${width}-${route.replaceAll('/','').replaceAll('?','-').replaceAll('=','-')||'landing'}.png`),fullPage:true});
   const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1);
   results.push({width,route,overflow});
  }
  await page.goto(origin+'/comparison');const selector=page.getByLabel('Comparison objective');await selector.waitFor();
  await page.getByText('Unavailable / insufficient transcript evidence',{exact:true}).waitFor();
  for(const objective of ['reach','engagement','creative_quality','balanced']){await selector.selectOption(objective);await page.waitForFunction(o=>document.querySelector('select')?.value===o,objective);await page.waitForFunction(()=>document.querySelector('section[aria-label="Canonical comparison"]')?.getAttribute('aria-busy')==='false');}
  console.log('Account interactions',width);await page.goto(origin+'/login');await page.getByRole('button',{name:'Continue with Google'}).click();await page.getByRole('alert').waitFor();
  assert((await page.getByRole('alert').textContent()).includes('could not be started'));
  await page.goto(origin+'/workspace');await page.getByText('5 of 5 analyses available',{exact:true}).waitFor();
  const menu=page.getByRole('button',{name:'Open navigation'});
  if(await menu.count()===1 && await menu.isVisible()){
    await menu.click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Tab');
    assert(await page.evaluate(()=>document.querySelector('dialog[open]')?.contains(document.activeElement)));
    await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});
  }
  await page.evaluate(()=>window.__fixture.setBalance(0));await page.getByText('Analysis status and usage history',{exact:true}).click();await page.getByRole('button',{name:'Refresh account balance'}).click();
  await page.getByRole('button',{name:'Free analysis limit reached'}).click();await page.getByRole('dialog').waitFor();
  await page.keyboard.press('Tab');assert(await page.evaluate(()=>document.querySelector('dialog[open]')?.contains(document.activeElement)));await page.keyboard.press('Escape');await page.getByRole('dialog').waitFor({state:'detached'});await page.getByRole('button',{name:'Free analysis limit reached'}).click();await page.getByRole('dialog').waitFor();
  await page.getByRole('button',{name:'View existing analyses'}).click();await page.getByRole('dialog').waitFor({state:'detached'});
  await page.evaluate(()=>window.__fixture.switchUser('B'));await page.getByRole('heading',{name:'Welcome, Acceptance B'}).waitFor();
  await page.evaluate(()=>{window.__fixture.deferClaims=true;window.__fixture.switchUser('A')});
  await page.waitForFunction(()=>window.__fixture.pendingClaims.length>0);
  await page.evaluate(()=>{window.__fixture.deferClaims=false;window.__fixture.switchUser('B')});
  await page.getByRole('heading',{name:'Welcome, Acceptance B'}).waitFor();
  await page.evaluate(()=>{sessionStorage.setItem('creatorlens_race_sentinel','preserved');window.__fixture.pendingClaims.splice(0).forEach(resolve=>resolve())});
  await page.evaluate(()=>new Promise(resolve=>setTimeout(resolve,30)));
  assert.equal(await page.evaluate(()=>sessionStorage.getItem('creatorlens_race_sentinel')),'preserved');
  await page.evaluate(()=>window.__fixture.rejectLogout=true);await page.getByRole('button',{name:'Sign out'}).click();await page.getByRole('heading',{name:'Sign in to your workspace'}).waitFor();
  assert.equal(await page.evaluate(()=>Object.keys(localStorage).some(k=>k.startsWith('creatorlens_'))),false);
  results.push({width,interactions:'four objectives, refresh, exhaustion dialog keyboard/Escape, mobile drawer, offline login error, account switch, stale-claim race, rejected SDK logout',passed:true});
  await context.close();
 }
 }finally{await browser.close();await new Promise(r=>server.close(r))}
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({method:'real Chromium; actual component code; isolated synthetic SDK/API, not Next proxy or OAuth',results,errors},null,2));
 console.log(JSON.stringify({screenshots:results.filter(r=>r.route).length,interactions:results.filter(r=>r.passed).length,overflows:results.filter(r=>r.overflow),errors},null,2));
 assert.equal(errors.length,0,'Component runtime errors found.');assert(!results.some(r=>r.overflow),'Responsive overflow found.');
}
main().catch(e=>{console.error(e.message);process.exitCode=1;setTimeout(()=>process.exit(1),500).unref()});
