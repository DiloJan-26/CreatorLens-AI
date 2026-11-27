/* Real Observability dashboard in Chromium; local mocked telemetry and diagnostic only. */
import fs from 'node:fs';import os from 'node:os';import path from 'node:path';import http from 'node:http';
import assert from 'node:assert/strict';import {createRequire} from 'node:module';import {fileURLToPath} from 'node:url';
const require=createRequire(import.meta.url),root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
if(!process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE)throw Error('Set ACCEPTANCE_PLAYWRIGHT_PACKAGE to an existing local Playwright installation.');
const {chromium}=require(process.env.ACCEPTANCE_PLAYWRIGHT_PACKAGE),webpack=require('next/dist/compiled/webpack/webpack').webpack;
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'creatorlens-llm-check-'));
const write=(name,value)=>{const file=path.join(temp,name);fs.writeFileSync(file,value);return file;};
const loader=write('loader.cjs',`const ts=require(${JSON.stringify(require.resolve('typescript'))});module.exports=s=>ts.transpileModule(s,{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;`);
const account=write('account.cjs',`exports.useAccount=()=>({account:{id:window.fixture.user}});`);
const next=write('navigation.cjs',`exports.usePathname=()=>location.pathname;`);
const api=write('api.cjs',`exports.checkEngineeringLlm=async project=>{window.fixture.calls.push(project);return new Promise(resolve=>window.fixture.resolve=resolve);};exports.getCostMetrics=async()=>({project_id:'owned-project',totals:{event_count:1,input_tokens:null,output_tokens:null,total_tokens:null,estimated_cost_usd:null},runs:[{id:'historical',status:'COMPLETED',prompt_name:'assistant',prompt_version:null,created_at:'2026-11-20T00:00:00Z',source_balance:{},input_tokens:null,output_tokens:null,total_tokens:null,retrieved_chunk_count:null,retrieval_latency_ms:null,llm_latency_ms:null,usage:{},llm_provider:'gemini',llm_model:'fixture'}]});`);
const session=write('session.cjs',`exports.getActiveProjectId=()=> 'owned-project';exports.subscribeToActiveProject=()=>()=>{};`);
const auth=write('auth.cjs',`exports.ApiError=class ApiError extends Error {};`);
const components=path.join(root,'src/components').replaceAll('\\','/');
const entry=write('entry.tsx',`
import React from 'react';import {createRoot} from 'react-dom/client';
import {CostDashboard} from '${components}/CostDashboard';
window.fixture={calls:[],resolve:null};
createRoot(document.getElementById('root')).render(<CostDashboard/>);
`);
await new Promise((resolve,reject)=>webpack({mode:'development',devtool:false,entry,output:{path:temp,filename:'bundle.js'},resolve:{extensions:['.tsx','.ts','.js'],modules:[path.join(root,'node_modules'),'node_modules'],alias:{'@/lib/api':api,'@/lib/app-session':session,'@/lib/auth-transport':auth,'next/navigation':next,'react$':require.resolve('react'),'react-dom/client':require.resolve('react-dom/client'),'react/jsx-runtime':require.resolve('react/jsx-runtime')}},plugins:[new webpack.NormalModuleReplacementPlugin(/^\.\/AccountProvider$/,account)],module:{rules:[{test:/\.tsx?$/,use:loader}]}},(err,stats)=>err||stats.hasErrors()?reject(err??Error(stats.toString())):resolve()));
function cssFiles(dir){if(!fs.existsSync(dir))return [];return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e=>e.isDirectory()?cssFiles(path.join(dir,e.name)):e.name.endsWith('.css')?[path.join(dir,e.name)]:[]);}
const css=cssFiles(path.join(root,'.next/static')).map(f=>fs.readFileSync(f,'utf8')).join('\n');assert(css.includes('llm-check-button'),'Build the frontend before browser acceptance.');
const server=http.createServer((req,res)=>{
 if(req.url==='/bundle.js'){res.setHeader('Content-Type','text/javascript');return res.end(fs.readFileSync(path.join(temp,'bundle.js')));}
 res.setHeader('Content-Type','text/html; charset=utf-8');res.end('<html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><style>'+css+'</style></head><body><div id="root"></div><script src="/bundle.js"></script></body></html>');
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const origin='http://127.0.0.1:'+server.address().port;let browser;
try {
 browser=await chromium.launch({headless:true});const context=await browser.newContext({viewport:{width:1365,height:1000}});
 await context.route('**/*',route=>route.request().url().startsWith(origin)?route.continue():route.abort());
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));await page.clock.install();await page.goto(origin);
 const button=page.getByRole('button',{name:'Check LLM availability',exact:true});await button.waitFor();
 await page.getByText('Coverage incomplete',{exact:true}).waitFor();
 assert.equal(await page.evaluate(()=>window.fixture.calls.length),0);
 assert(await page.locator('.llm-check-untested').count());
 assert(await page.locator('.page-title-row').getByRole('button',{name:'Check LLM availability'}).count());
 assert.deepEqual(await page.locator('.engineering-header-actions button').allTextContents(),['Refresh telemetry','Lock Engineering']);
 await page.getByRole('button',{name:'Refresh telemetry',exact:true}).click();
 assert.equal(await page.evaluate(()=>window.fixture.calls.length),0);
 await button.click();assert(await button.isDisabled());assert(await page.locator('.llm-check-checking').count());
 await page.evaluate(()=>document.querySelector('.llm-check-button').click());assert.equal(await page.evaluate(()=>window.fixture.calls.length),1);
 await page.evaluate(()=>window.fixture.resolve({status:'reachable',provider:'gemini',model:'fixture',checked_at:new Date().toISOString(),provider_invocation_count:1,retry_after_seconds:0,message:'The last check received a valid Gemini response.'}));
 await page.locator('.llm-check-reachable').waitFor();assert(await button.isDisabled());
 assert((await button.getAttribute('title')).includes('fixture'));assert(await page.getByText('Coverage incomplete',{exact:true}).count());
 await page.screenshot({path:path.join(temp,'llm-check-desktop.png'),fullPage:true});
 await page.clock.fastForward(60001);assert.equal(await page.evaluate(()=>window.fixture.calls.length),1);await button.click();
 await page.evaluate(()=>window.fixture.resolve({status:'blocked',provider:'gemini',model:'fixture',checked_at:new Date().toISOString(),provider_invocation_count:0,retry_after_seconds:0,message:'External provider execution is suspended.'}));
 await page.locator('.llm-check-failed').waitFor();assert((await button.getAttribute('title')).includes('suspended'));
 await button.click();await page.evaluate(()=>window.fixture.resolve({status:'reachable',provider_invocation_count:1,checked_at:'invalid'}));
 await page.getByRole('status').filter({hasText:'availability is unknown'}).waitFor();assert.equal(await page.locator('.llm-check-reachable').count(),0);
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:path.join(temp,'llm-check-mobile.png'),fullPage:true});
 await page.reload();await button.waitFor();assert.equal(await page.evaluate(()=>window.fixture.calls.length),0);assert(await page.locator('.llm-check-untested').count());
 assert.deepEqual(errors,[]);console.log('PASS: click-only LLM check, title placement, refresh/lock order, initial/checking/success/failure states, tooltip, duplicate prevention, cooldown, malformed response, independent coverage badge, reload reset and mobile layout.');console.log('Screenshots: '+temp);
} finally {await browser?.close();await new Promise(resolve=>server.close(resolve));}
