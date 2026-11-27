/* Real shared gate/provider in Chromium; Google identity and backend are local fixtures. */
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import http from 'node:http';
import assert from 'node:assert/strict';import {createRequire} from 'node:module';import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url),root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
if(!process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE)throw Error('Set ACCEPTANCE_PLAYWRIGHT_PACKAGE to an existing local Playwright installation.');
const {chromium}=require(process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE),webpack=require('next/dist/compiled/webpack/webpack').webpack;
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'creatorlens-engineering-'));
const write=(name,value)=>{const file=path.join(temp,name);fs.writeFileSync(file,value);return file;};
const loader=write('loader.cjs',`const ts=require(${JSON.stringify(require.resolve('typescript'))});module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;`);
const account=write('account.cjs',`exports.useAccount=()=>({account:{id:window.fixture.user}});`);
const next=write('navigation.cjs',`exports.usePathname=()=>location.pathname;`);
const api=write('api.cjs',`async function request(path,key){window.fixture.calls.push(path);const r=await fetch('/fixture/'+path,{method:path==='status'?'GET':'POST',headers:{'Content-Type':'application/json','X-Fixture-User':window.fixture.user},body:path==='status'?undefined:JSON.stringify({key})});const value=await r.json();if(!r.ok)throw Error(value.message);return value;}exports.getEngineeringAccess=()=>request('status');exports.unlockEngineering=key=>request('unlock',key);exports.lockEngineering=()=>request('lock');`);
const components=path.join(root,'src/components').replaceAll('\\','/');
const entry=write('entry.tsx',`
import React,{useState,useEffect} from 'react';import {createRoot} from 'react-dom/client';
import {EngineeringProvider,EngineeringGate,EngineeringIndicator,EngineeringLockButton} from '${components}/EngineeringAccess';
window.fixture={user:'fixture-user-a',calls:[],mounts:0};
function Dashboard(){useEffect(()=>{window.fixture.mounts++;},[]);return <div data-testid="dashboard"><h2>Protected dashboard</h2><EngineeringLockButton/></div>;}
function App(){const [view,setView]=useState(location.pathname),[identity,setIdentity]=useState(window.fixture.user);
function navigate(path){history.pushState(null,'',path);setView(path);}window.fixture.changeUser=()=>{window.fixture.user='fixture-user-b';setIdentity(window.fixture.user);};
return <EngineeringProvider key={identity}><main className="page-container"><aside className="engineering-nav-heading"><span>Engineering</span><EngineeringIndicator/></aside><nav><button onClick={()=>navigate('/evaluations')}>RAG Evaluation</button><button onClick={()=>navigate('/dashboard')}>LLM Observability</button></nav><EngineeringGate title={view==='/dashboard'?'LLM Observability':'RAG Evaluation'} icon="shield"><Dashboard/></EngineeringGate></main></EngineeringProvider>;}
createRoot(document.getElementById('root')).render(<App/>);
`);
await new Promise((resolve,reject)=>webpack({mode:'development',devtool:false,entry,output:{path:temp,filename:'bundle.js'},resolve:{extensions:['.tsx','.ts','.js'],modules:[path.join(root,'node_modules'),'node_modules'],alias:{'@/lib/api':api,'next/navigation':next,'react$':require.resolve('react'),'react-dom/client':require.resolve('react-dom/client'),'react/jsx-runtime':require.resolve('react/jsx-runtime')}},plugins:[new webpack.NormalModuleReplacementPlugin(/^\.\/AccountProvider$/,account)],module:{rules:[{test:/\.tsx?$/,use:loader}]}},(err,stats)=>err||stats.hasErrors()?reject(err??Error(stats.toString())):resolve()));
function cssFiles(dir){if(!fs.existsSync(dir))return [];return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?cssFiles(path.join(dir,e.name)):e.name.endsWith('.css')?[path.join(dir,e.name)]:[]);}
const css=cssFiles(path.join(root,'.next/static')).map(f=>fs.readFileSync(f,'utf8')).join('\n');assert(css.includes('engineering-unlock-panel'),'Build the frontend before browser acceptance.');
const grants=new Map();let offset=0,failed=false,configured=true;const key='offline-browser-engineering-key-0123456789';
const server=http.createServer(async(req,res)=>{
 if(req.url.startsWith('/fixture/')){
  const user=req.headers['x-fixture-user']??'fixture-user-a';const status=()=>({configured,unlocked:configured&&(grants.get(user)??0)>Date.now()+offset,expires_in:Math.max(0,Math.ceil(((grants.get(user)??0)-Date.now()-offset)/1000)),duration_seconds:1800});
  let body='';for await(const chunk of req)body+=chunk;
  res.setHeader('Content-Type','application/json');
  if(failed){res.statusCode=503;return res.end(JSON.stringify({message:'Synthetic access service unavailable.'}));}
  if(req.url==='/fixture/unlock'){if(JSON.parse(body).key!==key){res.statusCode=403;return res.end(JSON.stringify({message:'The Engineering access key is incorrect.'}));}grants.set(user,Date.now()+offset+1800000);}
  if(req.url==='/fixture/lock')grants.delete(user);
  return res.end(JSON.stringify(status()));
 }
 if(req.url==='/bundle.js'){res.setHeader('Content-Type','text/javascript');return res.end(fs.readFileSync(path.join(temp,'bundle.js')));}
 res.setHeader('Content-Type','text/html');res.end('<html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"/><style>'+css+'</style></head><body><div id="root"></div><script src="/bundle.js"></script></body></html>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;let browser;
try {
 browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1365,height:1000}});
 await context.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.clock.install();
 await page.goto(origin+'/evaluations');await page.getByLabel('Engineering access key',{exact:true}).waitFor();
 assert.equal(await page.locator('[data-testid="dashboard"]').count(),0);assert.equal(await page.evaluate(()=>window.fixture.mounts),0);
 await page.getByLabel('Engineering access key',{exact:true}).fill('incorrect');await page.getByRole('button',{name:'Unlock Engineering',exact:true}).click();
 await page.getByText('The Engineering access key is incorrect.',{exact:true}).waitFor();assert.equal(await page.getByLabel('Engineering access key',{exact:true}).inputValue(),'');
 await page.screenshot({path:path.join(temp,'engineering-locked.png'),fullPage:true});
 const second=await context.newPage();await second.goto(origin+'/dashboard');await second.getByLabel('Engineering access key',{exact:true}).waitFor();
 await page.getByLabel('Engineering access key',{exact:true}).fill(key);await page.getByRole('button',{name:'Unlock Engineering',exact:true}).click();
 await page.getByTestId('dashboard').waitFor();await second.getByTestId('dashboard').waitFor();
 assert(!(await page.evaluate(()=>JSON.stringify({local:Object.entries(localStorage),session:Object.entries(sessionStorage)}))).includes(key));
 await page.getByRole('button',{name:'LLM Observability',exact:true}).click();await page.getByTestId('dashboard').waitFor();
 assert.equal(await page.getByRole('heading',{name:'Unlock Engineering',exact:true}).count(),0);
 await page.reload();await page.getByTestId('dashboard').waitFor();
 assert.equal(await page.evaluate(()=>window.fixture.calls.filter(c=>c==='unlock').length),0);
 await page.screenshot({path:path.join(temp,'engineering-unlocked.png'),fullPage:true});
 await page.getByRole('button',{name:'Lock Engineering',exact:true}).click();
 await page.getByLabel('Engineering access key',{exact:true}).waitFor();await second.getByLabel('Engineering access key',{exact:true}).waitFor();
 assert.equal(grants.has('fixture-user-a'),false);
 await page.getByLabel('Engineering access key',{exact:true}).fill(key);await page.getByRole('button',{name:'Unlock Engineering',exact:true}).click();await page.getByTestId('dashboard').waitFor();
 const reads=await page.evaluate(()=>window.fixture.calls.filter(c=>c==='status').length);
 offset+=1800000;await page.clock.fastForward(1800000);assert.equal(await page.evaluate(()=>window.fixture.calls.filter(c=>c==='status').length),reads);await page.getByLabel('Engineering access key',{exact:true}).waitFor();
 await page.clock.resume();offset=0;
 await page.getByLabel('Engineering access key',{exact:true}).fill(key);await page.getByRole('button',{name:'Unlock Engineering',exact:true}).click();await page.getByTestId('dashboard').waitFor();
 await page.evaluate(()=>window.fixture.changeUser());await page.getByLabel('Engineering access key',{exact:true}).waitFor();assert.equal(await page.locator('[data-testid="dashboard"]').count(),0);
 failed=true;await page.reload();await page.getByText('Synthetic access service unavailable.',{exact:true}).waitFor();assert.equal(await page.locator('[data-testid="dashboard"]').count(),0);
 failed=false;configured=false;await page.reload();await page.getByText('Engineering access has not been configured.',{exact:true}).waitFor();assert(await page.getByRole('button',{name:'Unlock Engineering',exact:true}).isDisabled());
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(temp,'engineering-mobile.png'),fullPage:true});
 assert.deepEqual(errors,[]);console.log('PASS: locked pages never mount dashboard content; wrong key, shared page access, cross-tab unlock/lock, refresh persistence, fixed expiry, account switch, service failure, missing configuration and mobile layout.');console.log('Screenshots: '+temp);
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
